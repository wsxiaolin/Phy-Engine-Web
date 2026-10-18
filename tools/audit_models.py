#!/usr/bin/env python3
"""Audit GLB vs Unity prefab/FBX/material source data, item by item.

Checks per component:
  A. node hierarchy (prefab node names present in GLB)
  B. per-renderer material slots vs GLB primitive count
  C. per-material params vs parsed .mat (same transforms as extractor:
     color sRGB->linear, metallic, roughness=max(.05,1-smoothness),
     emissive=min(1,x), alphaMode)
  D. per-renderer world AABB: prefab+FBX theory vs GLB actual geometry
     (catches lost offsets / wrong scale / wrong unit / wrong baking)

Usage: python3 tools/audit_models.py [glb_dir] [out_json]
Defaults: glb_dir=build/assets/components  out_json=/tmp/audit_report.json
"""
import os, sys, json, struct, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unity_yaml import UnityAssets, parse_prefab, parse_material, scene_tree, UNITY_ROOT
from extract_components import (trs_matrix, _mmul, conv_pos, _srgb_color,
                                MIRROR_X, FBXCache, BUILTIN_PRIMS,
                                BUILTIN_GUID, _builtin_primitive_md)
from fbx_binary import parse as fbx_parse, mesh_data, p70

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
IDENT_M = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

# ---------------------------------------------------------------- GLB reading
def read_glb(path):
    with open(path, 'rb') as f:
        data = f.read()
    assert data[:4] == b'glTF', path
    jlen = struct.unpack('<I', data[12:16])[0]
    j = json.loads(data[20:20 + jlen])
    bin_chunk = b''
    off = 20 + jlen
    if off + 8 <= len(data):
        blen, btype = struct.unpack('<I4s', data[off:off + 8])
        if btype == b'BIN\x00':
            bin_chunk = data[off + 8:off + 8 + blen]
    return j, bin_chunk

def accessor_positions(j, bin_chunk, acc_idx):
    """Return flat float list of a VEC3 POSITION accessor (tight packing)."""
    acc = j['accessors'][acc_idx]
    bv = j['bufferViews'][acc['bufferView']]
    off = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
    n = acc['count'] * 3
    return list(struct.unpack_from(f'<{n}f', bin_chunk, off))

def compose_node_worlds(j):
    """node index -> world matrix (col-major flat 16)."""
    worlds = {}
    def walk(idx, parent):
        n = j['nodes'][idx]
        if 'matrix' in n:
            local = list(n['matrix'])
        else:
            t = n.get('translation', [0, 0, 0])
            r = n.get('rotation', [0, 0, 0, 1])
            s = n.get('scale', [1, 1, 1])
            local = trs_matrix({'position': t, 'rotation': r, 'scale': s},
                               mirror_x=False)
        w = _mmul(parent, local)
        worlds[idx] = w
        for ch in n.get('children', []) or []:
            walk(ch, w)
    for r in j['scenes'][0]['nodes']:
        walk(r, IDENT_M)
    return worlds

def aabb_of_corners(corners):
    xs = [c[0] for c in corners]; ys = [c[1] for c in corners]; zs = [c[2] for c in corners]
    return [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]

def xform_aabb(mn, mx, m):
    corners = []
    for x in (mn[0], mx[0]):
        for y in (mn[1], mx[1]):
            for z in (mn[2], mx[2]):
                corners.append([m[0]*x + m[4]*y + m[8]*z + m[12],
                                m[1]*x + m[5]*y + m[9]*z + m[13],
                                m[2]*x + m[6]*y + m[10]*z + m[14]])
    return aabb_of_corners(corners)

def glb_node_aabbs(j, bin_chunk):
    """glb node name -> (local mn,mx) over all its mesh prims; plus worlds."""
    worlds = compose_node_worlds(j)
    per_node = {}
    for idx, n in enumerate(j['nodes']):
        if 'mesh' not in n:
            continue
        mesh = j['meshes'][n['mesh']]
        mn = [1e9] * 3; mx = [-1e9] * 3
        for prim in mesh['primitives']:
            pos = accessor_positions(j, bin_chunk, prim['attributes']['POSITION'])
            for i in range(0, len(pos), 3):
                for a in range(3):
                    v = pos[i + a]
                    if v < mn[a]: mn[a] = v
                    if v > mx[a]: mx[a] = v
        if mn[0] > mx[0]:
            continue
        per_node[idx] = (mn, mx)
    return worlds, per_node

# ------------------------------------------------------------- prefab side
# FBXCache 复用提取器实现（extract_components.FBXCache）——审计 pf 侧理论值
# 必须与提取语义逐字节同源，避免审计器自造映射造成假阳/假阴。

def mesh_local_aabb(info, fid, node_name):
    # Unity 内置基元：与提取器 _builtin_primitive_md 逐字节同源（unit=1，无 fbx_M）
    if fid in BUILTIN_PRIMS:
        md = _builtin_primitive_md(fid)
        unit, verts, fbx_M = 1.0, md['positions'], None
    else:
        geo = info['geo_by_fileid'].get(fid)
        if geo is None:
            geo = info['model_geos'].get(node_name)
        # 无 next(iter()) 随机兜底：取错几何的比较毫无意义（宁缺勿错）
        if geo is None:
            return None
        md = mesh_data(geo)
        if not md:
            return None
        unit = info['unit']
        verts = md['positions']
        fbx_M = info['model_world_M'].get(fid)
    # 仅统计多边形引用的顶点：FBX 顶点表常含未被引用的孤儿顶点，
    # Unity 不会渲染它们（按索引缓冲渲染），全表统计会造成 bbox 假阳性
    polys = md.get('polys') or []
    if polys:
        ref = sorted({vi for poly in polys for vi in poly})
        verts = [c for vi in ref for c in verts[vi*3:vi*3+3]]
    if fbx_M and fbx_M != IDENT_M:
        nv = len(verts) // 3
        baked = [0.0] * (nv * 3)
        for i in range(nv):
            x, y, z = verts[i*3], verts[i*3+1], verts[i*3+2]
            baked[i*3]   = fbx_M[0]*x + fbx_M[4]*y + fbx_M[8]*z + fbx_M[12]
            baked[i*3+1] = fbx_M[1]*x + fbx_M[5]*y + fbx_M[9]*z + fbx_M[13]
            baked[i*3+2] = fbx_M[2]*x + fbx_M[6]*y + fbx_M[10]*z + fbx_M[14]
        verts = baked
    mn = [1e9] * 3; mx = [-1e9] * 3
    for i in range(0, len(verts), 3):
        p = conv_pos(verts[i:i+3], unit)
        for a in range(3):
            if p[a] < mn[a]: mn[a] = p[a]
            if p[a] > mx[a]: mx[a] = p[a]
    return mn, mx

def walk_prefab(node, parent_M, depth, out):
    W = _mmul(parent_M, trs_matrix(node['transform']))
    comps = {c['class']: c['data'] for c in node['components']}
    mf, mr = comps.get(33), comps.get(23)
    rec = {'node': node, 'world': W, 'depth': depth, 'mn': None, 'mx': None,
           'mats': [], 'name': node['name'], 'active': node.get('active', 1),
           'mesh_guid': None, 'mesh_fid': 0}
    if mf and mr:
        mesh_ref = mf.get('m_Mesh') or {}
        rec['mesh_guid'] = mesh_ref.get('guid') if isinstance(mesh_ref, dict) else None
        rec['mesh_fid'] = mesh_ref.get('fileID', 0) if isinstance(mesh_ref, dict) else 0
        rec['mats'] = [m.get('guid') if isinstance(m, dict) else m
                       for m in (mr.get('m_Materials') or [])]
    out.append(rec)
    for ch in node['children']:
        walk_prefab(ch, W, depth + 1, out)

# ------------------------------------------------------------- material cmp
def expected_material(mat):
    """Expected glTF material fields from parsed .mat, mirroring add_material."""
    exp = {}
    exp['baseColorFactor'] = _srgb_color(mat.get('color') or [1, 1, 1, 1])
    exp['metallicFactor'] = mat['metallic'] if mat.get('metallic') is not None else 0.0
    sm = mat.get('smoothness')
    exp['roughnessFactor'] = max(0.05, 1.0 - (sm if sm is not None else 0.3))
    emis = mat.get('emissionColor')
    if emis and (emis[0] or emis[1] or emis[2]):
        exp['emissiveFactor'] = [min(1.0, emis[0]), min(1.0, emis[1]), min(1.0, emis[2])]
    else:
        exp['emissiveFactor'] = None
    mode = mat.get('mode', 'opaque')
    exp['alphaMode'] = 'BLEND' if mode in ('fade', 'transparent') else (
        'MASK' if mode == 'cutout' else 'OPAQUE')
    return exp

TOL = 0.002
def close(a, b, tol=TOL):
    return abs(a - b) <= tol

# ---------------------------------------------------------------- audit one
def audit_one(prefab_path, glb_path, ua, fbx_cache):
    pf = parse_prefab(prefab_path)
    tree = scene_tree(pf)
    j, bin_chunk = read_glb(glb_path)
    issues = []
    pin_procedural = []

    # ---- A. node hierarchy ----
    # GLB scene 根 = prefab 根（extractor 从 root['children'] 起发射），根名不入 GLB
    pf_names = []
    def names_pf(n, acc):
        acc.append(str(n['name']))
        for c in n['children']:
            names_pf(c, acc)
    for root in tree:
        names_pf(root, pf_names)
    root_names = {str(root['name']) for root in tree}
    glb_names = [n.get('name', '') for n in j['nodes']]
    missing_nodes = [x for x in pf_names if x and x not in glb_names
                     and not x.lower().startswith('pin')
                     and x not in root_names]
    if missing_nodes:
        issues.append(f'NODES-MISSING: {missing_nodes}')

    # ---- prefab walk: renderers + world AABBs ----
    recs = []
    for root in tree:
        walk_prefab(root, IDENT_M, 0, recs)
    active_renderers = [r for r in recs if r['active'] and r['mesh_guid']]

    worlds, per_node = glb_node_aabbs(j, bin_chunk)
    # GLB 侧按 DFS 序给每个名字建立 mesh 节点出现列表；prefab 侧同样 DFS 序
    # 消费出现序号 —— 同名兄弟节点（Unity 允许重名）不可按名字合并 bbox。
    name2gidx = {}
    for idx, n in enumerate(j['nodes']):
        nm = n.get('name', '')
        if nm and n.get('mesh') is not None:
            name2gidx.setdefault(nm, []).append(idx)
    name_ctr = {}
    def next_gidx(nm):
        lst = name2gidx.get(nm) or []
        k = name_ctr.get(nm, 0)
        name_ctr[nm] = k + 1
        return [lst[k]] if k < len(lst) else []

    comp_pf_mn = [1e9]*3; comp_pf_mx = [-1e9]*3
    comp_glb_mn = [1e9]*3; comp_glb_mx = [-1e9]*3
    glb_mats = j['materials']

    # ---- B/C/D per renderer ----
    for r in active_renderers:
        # 提取器语义：skip_pin_meshes 自根起对所有后代生效——任何名为 pin* 的节点
        # 都不发射网格（其 FBX 内部变换烘焙全错，引脚由前端按 catalog 坐标程序化生成）。
        # 审计同口径：计入 pin_procedural，不算缺陷。
        is_pin = str(r['name'] or '').lower().startswith('pin')
        if is_pin:
            pin_procedural.append(r['name'])
            continue
        # D. geometry AABB (prefab theory)
        fbx_path = ua.guid_map.get(r['mesh_guid'])
        pf_mn = pf_mx = None
        if fbx_path and fbx_path.lower().endswith('.fbx'):
            info = fbx_cache.get(fbx_path)
            box = mesh_local_aabb(info, r['mesh_fid'], r['name'])
            if box:
                pf_mn, pf_mx = xform_aabb(box[0], box[1], r['world'])
        elif r['mesh_guid'] == BUILTIN_GUID and r['mesh_fid'] in BUILTIN_PRIMS:
            box = mesh_local_aabb(None, r['mesh_fid'], r['name'])
            if box:
                pf_mn, pf_mx = xform_aabb(box[0], box[1], r['world'])
        gidxs = next_gidx(str(r['name']))
        if not gidxs:
            issues.append(f'MESH-MISSING: renderer {r["name"]} has no GLB node/mesh')
            continue
        # B. slots vs prims
        nslots = len(r['mats'])
        nprims = sum(len(j['meshes'][j['nodes'][i]['mesh']]['primitives']) for i in gidxs)
        if nprims < nslots:
            issues.append(f'SLOTS: {r["name"]} glb prims={nprims} < prefab slots={nslots}')
        # C. material params per slot
        for si, g in enumerate(r['mats']):
            if not g:
                continue
            mp = ua.guid_map.get(g)
            if not mp or not mp.endswith('.mat'):
                continue
            src = parse_material(os.path.join(UNITY_ROOT, mp))
            src_name = os.path.splitext(os.path.basename(mp))[0]
            exp = expected_material(src)
            m = None
            for i in gidxs:
                prim = j['meshes'][j['nodes'][i]['mesh']]['primitives']
                if si < len(prim) and prim[si].get('material') is not None:
                    m = glb_mats[prim[si]['material']]
                    break
            if m is None:
                issues.append(f'MAT-SLOT-MISSING: {src_name} slot{si} on {r["name"]}')
                continue
            if m.get('name') != src_name:
                issues.append(f'MAT-NAME: slot{si} on {r["name"]}: glb={m.get("name")} src={src_name}')
            pbr = m.get('pbrMetallicRoughness', {})
            gc = pbr.get('baseColorFactor') or [1, 1, 1, 1]
            ec = exp['baseColorFactor']
            for ci in range(4):
                if not close(ec[ci], gc[ci], 0.01):
                    issues.append(f'COLOR {src_name} ch{ci}: exp={round(ec[ci],4)} glb={round(gc[ci],4)}')
                    break
            gm = pbr.get('metallicFactor', 1.0)
            if not close(exp['metallicFactor'], gm):
                issues.append(f'METALLIC {src_name}: exp={exp["metallicFactor"]} glb={gm}')
            gr = pbr.get('roughnessFactor', 1.0)
            if not close(exp['roughnessFactor'], gr):
                issues.append(f'ROUGHNESS {src_name}: exp={round(exp["roughnessFactor"],4)} glb={gr}')
            ge = m.get('emissiveFactor')
            ee = exp['emissiveFactor']
            if ee is not None:
                if not ge or any(not close(ee[i], ge[i]) for i in range(3)):
                    issues.append(f'EMISSIVE {src_name}: exp={ee} glb={ge}')
            elif ge and any(abs(x) > 0.01 for x in ge[:3]):
                issues.append(f'EMISSIVE-EXTRA {src_name}: glb={ge} src has none')
            ga = m.get('alphaMode', 'OPAQUE')
            if ga != exp['alphaMode']:
                issues.append(f'ALPHA {src_name}: exp={exp["alphaMode"]} glb={ga}')
        # D. geometry AABB vs glb actual
        gmn = [1e9]*3; gmx = [-1e9]*3
        for i in gidxs:
            mn, mx = per_node.get(i, ([1e9]*3, [-1e9]*3))
            wmn, wmx = xform_aabb(mn, mx, worlds[i])
            for a in range(3):
                gmn[a] = min(gmn[a], wmn[a]); gmx[a] = max(gmx[a], wmx[a])
        if pf_mn:
            for a, ax in enumerate('XYZ'):
                if not close(pf_mn[a], gmn[a], 0.003) or not close(pf_mx[a], gmx[a], 0.003):
                    issues.append(
                        f'BBOX-{ax} {r["name"]}: pf=[{pf_mn[a]:.4f},{pf_mx[a]:.4f}] '
                        f'glb=[{gmn[a]:.4f},{gmx[a]:.4f}]')
        for a in range(3):
            comp_pf_mn[a] = min(comp_pf_mn[a], pf_mn[a] if pf_mn else gmn[a])
            comp_pf_mx[a] = max(comp_pf_mx[a], pf_mx[a] if pf_mn else gmx[a])
            comp_glb_mn[a] = min(comp_glb_mn[a], gmn[a]); comp_glb_mx[a] = max(comp_glb_mx[a], gmx[a])

    return {
        'prefab': os.path.basename(prefab_path),
        'glb': os.path.basename(glb_path),
        'nodes_pf': len(pf_names), 'nodes_glb': len(glb_names),
        'renderers': len(active_renderers),
        'pin_procedural': pin_procedural,
        'aabb_pf': [round(v, 4) for v in comp_pf_mn + comp_pf_mx],
        'aabb_glb': [round(v, 4) for v in comp_glb_mn + comp_glb_mx],
        'issues': issues,
    }

def main():
    ua = UnityAssets()
    fbx_cache = FBXCache()
    glb_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, 'build/assets/components')
    out_json = sys.argv[2] if len(sys.argv) > 2 else '/tmp/audit_report.json'
    rows = []
    for p in sorted(glob.glob(os.path.join(
            UNITY_ROOT, 'Assets/Resources/Experiments/**/*.prefab'), recursive=True)):
        # ModelID 以 prefab 根节点 CircuitComponent(114) 字段为准（与提取器同源），
        # 文件名含连字符（And-Gate.prefab）不可直接映射 GLB 名
        model_id = os.path.splitext(os.path.basename(p))[0]
        try:
            pf = parse_prefab(p)
            tree = scene_tree(pf)
            mid = None
            if tree:
                for c in tree[0]['components']:
                    if c['class'] == 114 and c['data'].get('ModelID'):
                        mid = str(c['data']['ModelID'])
                        break
            if mid:
                model_id = mid
        except Exception:
            pass
        glb = os.path.join(glb_dir, model_id.replace(' ', '_') + '.glb')
        if not os.path.exists(glb):
            rows.append({'prefab': model_id, 'glb': None, 'issues': ['GLB-MISSING']})
            continue
        try:
            rows.append(audit_one(p, glb, ua, fbx_cache))
        except Exception as e:
            import traceback
            rows.append({'prefab': model_id, 'glb': glb,
                         'issues': [f'ERR {type(e).__name__}: {e}']})
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    nbad = sum(1 for r in rows if r.get('issues'))
    print(f'TOTAL {len(rows)} components, {nbad} with issues')
    for r in rows:
        if r.get('issues'):
            print(f"  {r['prefab']}: {'; '.join(r['issues'][:5])}"
                  + (' ...' if len(r['issues']) > 5 else ''))

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Unity 参照侧数据 dump：prefab/FBX/材质 → build/refdump/{ModelID}.json

用途：Unity 原版 vs web 端逐元件对比截图的「Unity 侧」数据源。
直接从 prefab YAML + FBX 二进制 + .mat 材质构建（不经过 build/assets/*.glb），
顶点展开/子网格/材质语义与 extract_components._emit_mesh 逐条对齐（审计已数值
验证 prefAB 理论值 == GLB 实际值）。浏览器端 compare.html 用 three.js 渲染该
JSON 与生产 GLB 并排对比。

输出 JSON 结构：
  modelId, name, nodes[{name, matrix(16, col-major glTF), slots:[{positions,
  normals, uvs, indices, material}]}], materials[{name, baseColorFactor,
  metallicFactor, roughnessFactor, emissiveFactor, alphaMode, texturePath}]

引脚口径：任何名为 pin* 的节点不输出网格（其 FBX 内部变换烘焙不可信，
web 端由程序化接线柱替代，两侧口径一致）。

用法：python3 tools/prefab_ref_dump.py [out_dir]
"""
import os, sys, json, math, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unity_yaml import UnityAssets, parse_prefab, scene_tree, parse_material, UNITY_ROOT
from extract_components import (trs_matrix, conv_pos, conv_normal, flip_winding,
                                MIRROR_X, FBXCache, BUILTIN_PRIMS, BUILTIN_GUID,
                                _builtin_primitive_md)
from fbx_binary import parse as fbx_parse, mesh_data

OUT_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build', 'refdump')
IDENT_M = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def bake_point(m, p):
    return [m[0]*p[0] + m[4]*p[1] + m[8]*p[2] + m[12],
            m[1]*p[0] + m[5]*p[1] + m[9]*p[2] + m[13],
            m[2]*p[0] + m[6]*p[1] + m[10]*p[2] + m[14]]


def expand_mesh(md, unit, fbx_M, mats_parsed):
    """复刻 _emit_mesh 的逐角展开：返回 [{positions, normals, uvs, indices, material}]"""
    verts = md['positions']
    if fbx_M and fbx_M != IDENT_M:
        nv = len(verts) // 3
        baked = [0.0] * (nv * 3)
        for i in range(nv):
            baked[i*3:i*3+3] = bake_point(fbx_M, verts[i*3:i*3+3])
        verts = baked

    def _bake_normal(n):
        if not fbx_M or fbx_M == IDENT_M:
            return list(n)
        return [fbx_M[0]*n[0] + fbx_M[4]*n[1] + fbx_M[8]*n[2],
                fbx_M[1]*n[0] + fbx_M[5]*n[1] + fbx_M[9]*n[2],
                fbx_M[2]*n[0] + fbx_M[6]*n[1] + fbx_M[10]*n[2]]

    polys = md['polys']
    nm = md.get('normals_mapping', 'ByPolygonVertex')
    nr = md.get('normals_raw') or []
    um = md.get('uvs_mapping', 'ByPolygonVertex')
    ur = md.get('uvs_raw') or []
    uvi = md.get('uv_index')
    mat_mapping = md.get('mat_mapping', 'AllSame')
    mat_indices = md.get('mat_indices') or []

    def _slot_of_poly(pi, corner):
        if mat_mapping == 'ByPolygon' and pi < len(mat_indices):
            return int(mat_indices[pi])
        if mat_mapping == 'ByPolygonVertex' and corner < len(mat_indices):
            return int(mat_indices[corner])
        return 0

    per_poly_meta = []
    corner = 0
    for pi, poly in enumerate(polys):
        if len(poly) < 3:
            corner += len(poly)
            continue
        slot = _slot_of_poly(pi, corner)
        metas = []
        for k, cx in enumerate(poly):
            bi = None
            if nr:
                if nm == 'ByPolygonVertex':
                    bi = (corner + k) * 3
                elif nm == 'ByVertice':
                    bi = cx * 3
                else:
                    bi = 0
                if bi >= len(nr):
                    bi = None
            ui = None
            if ur:
                if uvi is not None and (corner + k) < len(uvi):
                    ui = uvi[corner + k] * 2
                elif um == 'ByVertice':
                    ui = cx * 2
                else:
                    ui = (corner + k) * 2
                if ui + 1 >= len(ur):
                    ui = None
            metas.append((cx, bi, ui))
        per_poly_meta.append((slot, metas))
        corner += len(poly)

    # Unity 导入语义：子网格号 = FBX 材质索引按出现升序重编
    used = sorted({s for s, _ in per_poly_meta})
    rank = {m: i for i, m in enumerate(used)}

    groups = {}
    for slot, metas in per_poly_meta:
        g = groups.setdefault(rank[slot], {'positions': [], 'normals': [], 'uvs': [], 'indices': [], 'vc': 0})
        base = g['vc']
        for (cx, bi, ui) in metas:
            g['positions'].extend(conv_pos(verts[cx*3:cx*3+3], unit))
            if nr and bi is not None:
                g['normals'].extend(conv_normal(_bake_normal(nr[bi:bi+3])))
            if ur and ui is not None:
                g['uvs'].extend([ur[ui], 1.0 - ur[ui+1]])
            g['vc'] += 1
        for k in range(1, len(metas) - 1):
            g['indices'].extend([base, base + k, base + k + 1])

    slots = []
    for slot in sorted(groups):
        g = groups[slot]
        if MIRROR_X:
            g['indices'] = flip_winding(g['indices'])
        if not g['normals']:
            g['normals'] = face_normals(g['positions'], g['indices'])
        mi = slot if slot < len(mats_parsed) else None
        slots.append({'positions': [round(v, 6) for v in g['positions']],
                      'normals': [round(v, 4) for v in g['normals']],
                      'uvs': [round(v, 5) for v in g['uvs']] if g['uvs'] else None,
                      'indices': g['indices'], 'material': mi})
    return slots


def face_normals(positions, indices):
    normals = [0.0] * (len(positions) // 3 * 3)
    for i in range(0, len(indices), 3):
        a, b, c = indices[i]*3, indices[i+1]*3, indices[i+2]*3
        ux, uy, uz = positions[b]-positions[a], positions[b+1]-positions[a+1], positions[b+2]-positions[a+2]
        vx, vy, vz = positions[c]-positions[a], positions[c+1]-positions[a+1], positions[c+2]-positions[a+2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        for idx in (a, b, c):
            normals[idx] += nx; normals[idx+1] += ny; normals[idx+2] += nz
    out = []
    for i in range(0, len(normals), 3):
        l = math.sqrt(normals[i]**2 + normals[i+1]**2 + normals[i+2]**2) or 1.0
        out.extend([normals[i]/l, normals[i+1]/l, normals[i+2]/l])
    return out


def dump_component(prefab_path, ua, fbx_cache, out_dir):
    pf = parse_prefab(prefab_path)
    tree = scene_tree(pf)
    if not tree:
        return None
    root = tree[0]
    cc = next((c['data'] for c in root['components'] if c['class'] == 114), None)
    if not cc or not cc.get('ModelID'):
        return None
    model_id = cc['ModelID']

    materials = []

    def mat_index(mat_parsed, mat_path):
        # 材质去重（同路径同参数只存一份）
        for i, m in enumerate(materials):
            if m['__path'] == mat_path:
                return i
        # 与提取器同口径：maintex guid → 工程内相对路径（ua.guid_map）
        _tex = None
        if mat_parsed.get('maintex'):
            _mp = ua.guid_map.get(mat_parsed['maintex'])
            if _mp:
                _tex = ('Assets/' + _mp.split('Assets/', 1)[-1]) if 'Assets/' in _mp else _mp
        m = {
            'name': os.path.splitext(os.path.basename(mat_path))[0] if mat_path else 'default',
            'baseColorFactor': mat_parsed.get('color') or [1, 1, 1, 1],
            'metallicFactor': mat_parsed.get('metallic') if mat_parsed.get('metallic') is not None else 0.0,
            'roughnessFactor': max(0.05, 1.0 - (mat_parsed.get('smoothness') if mat_parsed.get('smoothness') is not None else 0.3)),
            'emissiveFactor': mat_parsed.get('emissionColor') or None,
            'alphaMode': 'BLEND' if mat_parsed.get('mode') in ('fade', 'transparent') else ('MASK' if mat_parsed.get('mode') == 'cutout' else 'OPAQUE'),
            'texturePath': _tex,
            '__path': mat_path,
        }
        materials.append(m)
        return len(materials) - 1

    nodes = []

    def walk(node, parent_idx):
        comps = {c['class']: c['data'] for c in node['components']}
        mf, mr = comps.get(33), comps.get(23)
        slots = []
        is_pin = str(node['name'] or '').lower().startswith('pin')
        if mf and mr and node.get('active', 1) and not is_pin:
            mesh_ref = mf.get('m_Mesh')
            if isinstance(mesh_ref, dict) and mesh_ref.get('guid'):
                mats_parsed = []
                for mref in (mr.get('m_Materials') or []):
                    if isinstance(mref, dict) and mref.get('guid'):
                        mp = ua.guid_map.get(mref['guid'])
                        if mp and mp.endswith('.mat'):
                            m = parse_material(os.path.join(UNITY_ROOT, mp))
                            mats_parsed.append((m, mp))
                            continue
                    mats_parsed.append((None, None))
                if mesh_ref['guid'] == BUILTIN_GUID and mesh_ref.get('fileID') in BUILTIN_PRIMS:
                    md = _builtin_primitive_md(mesh_ref['fileID'])
                    slots = expand_mesh(md, 1.0, None, mats_parsed)
                else:
                    fbx_path = ua.guid_map.get(mesh_ref['guid'])
                    if fbx_path and fbx_path.lower().endswith('.fbx'):
                        info = fbx_cache.get(fbx_path)
                        fid = mesh_ref.get('fileID', 0)
                        geo = info['geo_by_fileid'].get(fid)
                        if geo is None:
                            geo = info['model_geos'].get(node['name'])
                        if geo is not None:
                            md = mesh_data(geo)
                            if md:
                                fbx_M = info.get('model_world_M', {}).get(fid)
                                slots = expand_mesh(md, info['unit'], fbx_M, mats_parsed)
        rec = {'name': node['name'],
               'matrix': trs_matrix(node['transform']),
               'slots': []}
        for s in slots:
            mi = s['material']
            mp = (mats_parsed[mi][1] if mi is not None and mi < len(mats_parsed) else None)
            rec['slots'].append({'positions': s['positions'], 'normals': s['normals'],
                                 'uvs': s['uvs'], 'indices': s['indices'],
                                 'material': -1, '_matpath': mp})
        idx = len(nodes)
        nodes.append(rec)
        children = []
        for ch in node['children']:
            children.append(walk(ch, idx))
        rec['children'] = children
        return idx

    walk(root, -1)
    # 统一材质号：_matpath → materials 索引
    for rec in nodes:
        for s in rec['slots']:
            mp = s.pop('_matpath', None)
            if mp:
                m = parse_material(os.path.join(UNITY_ROOT, mp))
                s['material'] = mat_index(m, mp)
            else:
                s['material'] = mat_index({}, '__default__')
    for m in materials:
        m.pop('__path', None)
        c = m['baseColorFactor']
        m['baseColorFactor'] = [round(v, 5) for v in c]
        if m['emissiveFactor']:
            m['emissiveFactor'] = [round(min(1.0, v), 5) for v in m['emissiveFactor'][:3]]

    out = {'modelId': model_id,
           'name': cc.get('FriendlyName', model_id),
           'prefab': os.path.basename(prefab_path),
           'nodes': nodes, 'materials': materials}
    with open(os.path.join(out_dir, f'{model_id}.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    return model_id


def main():
    out_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else OUT_DEFAULT)
    os.makedirs(out_dir, exist_ok=True)
    ua = UnityAssets()
    fbx_cache = FBXCache()
    n = 0
    for p in sorted(glob.glob(os.path.join(UNITY_ROOT, 'Assets/Resources/Experiments/**/*.prefab'), recursive=True)):
        try:
            mid = dump_component(p, ua, fbx_cache, out_dir)
            if mid:
                n += 1
                print(f'OK  {mid}')
        except Exception as e:
            import traceback
            print(f'ERR {os.path.basename(p)}: {e}')
            traceback.print_exc()
    print(f'Total {n} refdump -> {out_dir}')


if __name__ == '__main__':
    main()

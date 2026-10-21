#!/usr/bin/env python3
"""diag5.py — 5 件 FAIL 的提取链诊断（2026-10-22）。

对每件 prefab 逐节点打印：
  1) 节点 TRS + m_Mesh(guid:fileID)
  2) guid→FBX 路径；.meta 权威 fileID→对象名
  3) 解析到的几何对象名（权威名 / 遍历序名 / 名称兜底 三路对比）
  4) raw 顶点 bbox（FBX 单位）、Geometric(T/R/S)
  5) 材质槽名 + 主贴图名
  6) Unity 语义期望世界 bbox：prefab TRS 链 × conv × geo_M × raw（nobake 语义）
目的：定位「绑错 mesh / geo_M 错 / 材质贴图错」到底哪个环节。
用法：python3 tools/diag5.py [ModelID ...]（默认 5 件 FAIL）
"""
import os, sys, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unity_yaml import (UnityAssets, parse_prefab, scene_tree, parse_material,
                        UNITY_ROOT, fbx_meta_mesh_names, safe_name)
from fbx_binary import parse as fbx_parse, mesh_data, p70, p70v3
import extract_components as EC

TARGETS = sys.argv[1:] or ['Mutual_Inductor', 'Transformer', 'Air_Switch',
                           'Logic_Input', 'Logic_Output']
# prefab 文件名（ModelID 去下划线带空格）
PF_NAME = {t: t.replace('_', ' ') + '.prefab' for t in TARGETS}

ua = UnityAssets()


def find_prefab(mid):
    import glob
    for p in glob.glob(os.path.join(UNITY_ROOT, 'Assets/Resources/Experiments/**/*.prefab'), recursive=True):
        if os.path.basename(p) == PF_NAME[mid]:
            return p
    return None


def bbox(vs):
    xs, ys, zs = vs[0::3], vs[1::3], vs[2::3]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def fmt(b):
    return '[' + ', '.join(f'{v:.2f}' for v in b) + ']'


def trs_str(t):
    def g(k, n, d):
        v = t.get(k) or d
        return v if isinstance(v, list) else [v.get(c, 0) for c in 'xyz'[:n]]
    p, r, s = g('position', 3, [0, 0, 0]), g('rotation', 4, [0, 0, 0, 1]), g('scale', 3, [1, 1, 1])
    return (f"p=({p[0]:.3f},{p[1]:.3f},{p[2]:.3f}) "
            f"r=({r[0]:.3f},{r[1]:.3f},{r[2]:.3f},{r[3]:.3f}) "
            f"s=({s[0]:.3f},{s[1]:.3f},{s[2]:.3f})")


for mid in TARGETS:
    pf_path = find_prefab(mid)
    print(f'######## {mid} ########')
    if not pf_path:
        print('  prefab NOT FOUND'); continue
    pf = parse_prefab(pf_path)
    tree = scene_tree(pf)
    root = tree[0]
    cc = next((c['data'] for c in root['components'] if c['class'] == 114), None)

    def walk(node, depth):
        ind = '  ' * depth
        comps = {c['class']: c['data'] for c in node['components']}
        mf, mr = comps.get(33), comps.get(23)
        active = node.get('active', 1)
        print(f'{ind}[{node["name"]}] active={active} {trs_str(node["transform"])}')
        if mf and mr:
            mref = mf.get('m_Mesh') or {}
            guid, fid = mref.get('guid'), mref.get('fileID', 0)
            print(f'{ind}  mesh guid={guid[:12] if guid else None}.. fileID={fid}')
            if guid == EC.BUILTIN_GUID:
                print(f'{ind}  -> 内置基元 fileID={fid}')
            else:
                fbx_rel = ua.guid_map.get(guid)
                if not fbx_rel or not fbx_rel.lower().endswith('.fbx'):
                    print(f'{ind}  -> guid 未映射到 FBX: {fbx_rel}')
                else:
                    f = fbx_parse(os.path.join(UNITY_ROOT, fbx_rel))
                    meta = fbx_meta_mesh_names(fbx_rel)
                    auth = meta.get(fid)
                    # 遍历序 fids
                    iter_map = {}
                    name_geo = {}
                    for i, (oid, n) in enumerate(f.by_type('Model')):
                        g = f.geometry_of(oid)
                        if g:
                            nm = (n.prop(1) or n.name).split('\x00', 1)[0]
                            iter_map[4300000 + 2 * i] = nm
                            name_geo.setdefault(nm, (oid, g[1]))
                    resolved = '权威' if auth else ('遍历序' if fid in iter_map else '名称兜底/丢失')
                    print(f'{ind}  -> FBX={os.path.basename(fbx_rel)} 权威名={auth} 遍历名={iter_map.get(fid)} 节点名={node["name"]} 解析路={resolved}')
                    # 找到实际会用的几何
                    geo = None; used_name = None
                    if auth and auth in name_geo:
                        geo = name_geo[auth][1]; used_name = auth
                    elif fid in iter_map and iter_map[fid] in name_geo:
                        geo = name_geo[iter_map[fid]][1]; used_name = iter_map[fid]
                    elif node['name'] in name_geo:
                        geo = name_geo[node['name']][1]; used_name = node['name']
                    if geo is None:
                        print(f'{ind}  -> ⚠️ 几何解析失败（GLB 中该节点无 mesh）')
                        print(f'{ind}     FBX 全部对象: {list(name_geo.keys())}')
                    else:
                        md = mesh_data(geo)
                        bmin, bmax = bbox(md['positions'])
                        # Geometric
                        oid = name_geo[used_name][0]
                        n = f.objects[oid][1]
                        Tg = p70v3(n, 'GeometricTranslation')
                        Rg = p70v3(n, 'GeometricRotation')
                        Sg = p70v3(n, 'GeometricScaling')
                        print(f'{ind}  -> 用几何={used_name} rawBBox={fmt(bmin)}..{fmt(bmax)} (FBX单位)')
                        print(f'{ind}     GeomT={Tg} GeomR={Rg} GeomS={Sg}')
                    # 材质槽
                    mats = mr.get('m_Materials') or []
                    for m in mats:
                        mg = m.get('guid') if isinstance(m, dict) else None
                        if not mg: continue
                        mp = ua.guid_map.get(mg)
                        if mp:
                            pm = parse_material(os.path.join(UNITY_ROOT, mp))
                            tex = ua.guid_map.get(pm.get('maintex')) if pm.get('maintex') else None
                            print(f'{ind}     mat={os.path.basename(mp)} tex={os.path.basename(tex) if tex else None}')
        for ch in node['children']:
            walk(ch, depth + 1)

    for ch in root['children']:
        walk(ch, 1)
    print()

#!/usr/bin/env python3
"""diag_transform.py — 诊断 prefab 节点 TRS vs FBX Model Lcl 的双重变换疑云。

对指定元件 prefab：逐 MeshFilter 节点打印
  1. prefab 节点 TRS（Unity 空间，米）
  2. 所引 FBX Model 的 Lcl T/R/S（FBX 原始单位）
  3. FBX Model 相对 FBX 根的世界矩阵 fbx_M（提取器当前烘进顶点的）
  4. 顶点原始范围（Geometry 局部）
  5. Unity 语义理论世界范围 = prefabTRS × ancestorChain(prefab 内) × vertex
     （顶点在 Model 局部，prefab 层级承担全部变换）
  6. 提取器实际 GLB 范围 = prefabTRS × fbx_M × vertex（双重变换）
若 5 与官方预览吻合而 6 偏移/巨大 → 双重变换实锤。
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(__file__))
from unity_yaml import UnityAssets, parse_prefab, scene_tree, fbx_meta_mesh_names, UNITY_ROOT
from fbx_binary import parse as fbx_parse, mesh_data, p70
import extract_components as ec

def mat_mul(A, B):
    return [sum(A[r*4+k]*B[k*4+c] for k in range(4)) for r in range(4) for c in range(4)]

def mat_vec(M, v):
    return [M[0]*v[0]+M[4]*v[1]+M[8]*v[2]+M[12],
            M[1]*v[0]+M[5]*v[1]+M[9]*v[2]+M[13],
            M[2]*v[0]+M[6]*v[1]+M[10]*v[2]+M[14]]

def bbox_apply(M, md):
    pos = md['positions']
    mn = [1e9]*3; mx = [-1e9]*3
    for i in range(0, len(pos), 3):
        w = mat_vec(M, pos[i:i+3])
        for j in range(3):
            mn[j] = min(mn[j], w[j]); mx[j] = max(mx[j], w[j])
    return mn, mx

def diag(prefab_path, name_filter=None):
    print(f"===== {os.path.basename(prefab_path)}")
    ua = UnityAssets()
    pf = parse_prefab(prefab_path)
    tree = scene_tree(pf)

    def walk(node, parent_M):
        comps = {c['class']: c['data'] for c in node['components']}
        mf, mr = comps.get(33), comps.get(23)
        nm = str(node['name'] or '?')
        is_pin = nm.lower().startswith('pin')
        if mf and mr and not is_pin:
            mesh_ref = mf.get('m_Mesh') or {}
            guid, fid = mesh_ref.get('guid'), mesh_ref.get('fileID', 0)
            # prefab 侧世界矩阵（root identity）
            t = node['transform']
            my_M = ec.trs_matrix(t)
            world_M = mat_mul(parent_M, my_M)
            if guid and guid != ec.BUILTIN_GUID:
                fbx_path = ua.guid_map.get(guid)
                if fbx_path and fbx_path.lower().endswith('.fbx'):
                    info = ec.FBXCache().get(fbx_path)
                    geo = info['geo_by_fileid'].get(fid) or info['model_geos'].get(nm)
                    fbx_M = info.get('model_world_M', {}).get(fid)
                    if geo is not None:
                        md = mesh_data(geo)
                        if md:
                            # Unity 语义：顶点在 Model 局部，prefab 层级承担全部
                            unity_mn, unity_mx = bbox_apply(world_M, md)
                            # 提取器语义：再烘 fbx_M
                            glb_M = mat_mul(world_M, fbx_M) if fbx_M else world_M
                            glb_mn, glb_mx = bbox_apply(glb_M, md)
                            unit = info['unit']
                            print(f"  [{nm}] mesh fid={fid} unit={unit:.4f}")
                            print(f"    prefab TRS: T={t['position']} S={t['scale']}")
                            print(f"    Unity语义世界 bbox(顶点局部): {[round(v*unit,4) for v in unity_mn]} .. {[round(v*unit,4) for v in unity_mx]}")
                            print(f"    提取器GLB bbox(烘fbx_M):     {[round(v*unit,4) for v in glb_mn]} .. {[round(v*unit,4) for v in glb_mx]}")
        for ch in node['children']:
            walk(ch, mat_mul(parent_M, ec.trs_matrix(ch['transform'])))

    for ch in tree[0]['children']:
        walk(ch, [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]][0:4] and [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1])

if __name__ == '__main__':
    diag(sys.argv[1])

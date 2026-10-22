#!/usr/bin/env python3
"""Export room + table GLB from 房间.FBX with Unity .mat materials."""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(__file__))
from unity_yaml import UnityAssets, parse_material, UNITY_ROOT
from extract_components import GLB, _emit_mesh, trs_matrix
from fbx_binary import parse as fbx_parse, mesh_data, p70

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'build', 'assets'))
MAT_MAP = {
    'Table001': 'table-0.mat', 'floor': 'floor-0.mat', 'Room-back': 'Room-0.mat',
    'Room L': 'Room-0.mat', 'door': 'door-0.mat', 'Windows': 'Windows.mat',
    'Persiana': 'Persiana.mat', 'Curtain': 'Persiana.mat', 'glass': '玻璃.mat',
}

def euler_to_quat(rx, ry, rz):
    rx, ry, rz = map(math.radians, (rx, ry, rz))
    cx, sx = math.cos(rx/2), math.sin(rx/2)
    cy, sy = math.cos(ry/2), math.sin(ry/2)
    cz, sz = math.cos(rz/2), math.sin(rz/2)
    # 3ds Max XYZ euler
    return [
        sx*cy*cz + cx*sy*sz,
        cx*sy*cz - sx*cy*sz,
        cx*cy*sz + sx*sy*cz,
        cx*cy*cz - sx*sy*sz,
    ]

def main():
    ua = UnityAssets()
    glb = GLB()
    fbx_path = os.path.join(UNITY_ROOT, 'Assets/Physics-Lab/Rooms/Meshes/房间.FBX')
    f = fbx_parse(fbx_path)
    mats_dir = os.path.join(UNITY_ROOT, 'Assets/Physics-Lab/Rooms/Materials')

    # material GUID lookup: build name->guid map from Rooms/Materials
    mat_guid = {}
    for mat_file in MAT_MAP.values():
        mp = os.path.join(mats_dir, mat_file)
        meta = mp + '.meta'
        if os.path.exists(meta):
            with open(meta) as fh:
                for line in fh:
                    if line.startswith('guid:'):
                        mat_guid[mat_file] = line.split('guid:')[1].strip()
                        break

    model_geo = {}
    for oid, n in f.by_type('Model'):
        geo = f.geometry_of(oid)
        if geo:
            objname = (n.prop(1) or 'Model').split('\x00', 1)[0]
            model_geo[objname] = (oid, geo)

    info = {'unit': 0.01}
    node_indices = []
    for name, (oid, geo) in model_geo.items():
        md = mesh_data(geo[1])
        if not md: continue
        node = {'name': name}
        mr = {'m_Materials': []}
        gf = mat_guid.get(MAT_MAP.get(name, ''))
        if gf:
            mr['m_Materials'] = [{'guid': gf}]
        mesh_idx = _emit_mesh(glb, node, md, info, mr, ua)
        # local transform from FBX node
        n = f.objects[oid][1]
        tr = p70(n, 'Lcl Translation') or [0, 0, 0]
        rot = p70(n, 'Lcl Rotation') or [0, 0, 0]
        sc = p70(n, 'Lcl Scaling') or [1, 1, 1]
        q = euler_to_quat(*rot)
        # 2026-10-22 统一镜像语义：房间为平面结构，节点走纯转换（不镜像），
        # x 镜像统一烘进 Room 根矩阵（Room_M·S），房间渲染与旧管线逐位一致。
        m = trs_matrix({'position': list(map(float, tr)), 'rotation': q,
                        'scale': list(map(float, sc))}, mirror_x=False)
        node_indices.append(glb.add_node(name, mesh=mesh_idx, matrix=m))

    # 房间.FBX geometry is authored Z-up (UpAxis=1 declared but data is Z-up);
    # components are Y-up. Bake a -90deg X rotation under a single root so the
    # room matches the component/three.js Y-up convention.
    # Room_M·S：右乘 diag(-1,1,1)（列主序 flat，只取反 col0/x 列），
    # 承担旧管线「每层共轭+顶点镜像」的净 x 镜像（顶层一次 S 语义）。
    root = glb.add_node('Room', children=node_indices,
                        matrix=[-1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1])
    _ = root

    os.makedirs(OUT, exist_ok=True)
    out_path = os.path.join(OUT, 'room.glb')
    glb.write(out_path)
    print('wrote', out_path, os.path.getsize(out_path), 'bytes', 'models:', len(model_geo))

if __name__ == '__main__':
    main()

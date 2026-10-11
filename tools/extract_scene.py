#!/usr/bin/env python3
"""Extract room/table/lights from Unity scenes into scene.json + GLBs."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from unity_yaml import UnityAssets, load_yaml_docs, parse_material, UNITY_ROOT
from extract_components import GLB, FBXCache, trs_matrix, MIRROR_X

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'build', 'assets'))

def docs_by_name(path):
    docs = load_yaml_docs(path)
    gos, transforms, comps = {}, {}, {}
    for (cid, fid, d) in docs:
        if cid == 1: gos[fid] = d
        elif cid == 4: transforms[fid] = d
    # map transform -> gameobject name & components
    out = {}
    light_data = []
    for tfid, tr in transforms.items():
        go = gos.get(tr.get('m_GameObject', {}).get('fileID', 0), {})
        name = go.get('m_Name', '')
        entry = {'transform': tr, 'go': go, 'fid': tfid}
        out.setdefault(name, []).append(entry)
    return docs, out

def resolve_mesh(mesh_ref, ua, fbx_cache, out_name):
    guid = mesh_ref.get('guid', '')
    path = ua.guid_map.get(guid)
    if not path or not path.lower().endswith('.fbx'):
        return None
    info = fbx_cache.get(path)
    f = info['fbx']
    # fileID 4300000 + 2*i? try model-name match impossible here; take by fileID order
    geos = f.by_type('Geometry')
    fileid = mesh_ref.get('fileID', 4300000)
    idx = (fileid - 4300000) // 2 if fileid >= 4300000 else 0
    if 0 <= idx < len(geos):
        gid, gn = geos[idx]
        return info, gn
    return (info, geos[0][1]) if geos else None

def main():
    ua = UnityAssets()
    fbx_cache = FBXCache()
    result = {'table': None, 'room': [], 'lights': [], 'camera': {}}

    # ---- Room Default.unity ----
    path = os.path.join(UNITY_ROOT, 'Assets/Circuits/Scenes/Room Default.unity')
    docs, byname = docs_by_name(path)
    for name, entries in byname.items():
        for e in entries:
            tr = e['transform']
            # lights: class 108 Light on GO
            for (cid, fid, d) in docs:
                if cid == 108 and d.get('m_GameObject', {}).get('fileID') == tr.get('m_GameObject', {}).get('fileID'):
                    result['lights'].append({
                        'name': name,
                        'type': 'point' if d.get('m_Type', 0) == 0 else ('directional' if d.get('m_Type') == 1 else 'spot'),
                        'position': [tr.get('m_LocalPosition', {}).get('x', 0), tr.get('m_LocalPosition', {}).get('y', 0), tr.get('m_LocalPosition', {}).get('z', 0)],
                        'rotation': [tr.get('m_LocalRotation', {}).get('x', 0), tr.get('m_LocalRotation', {}).get('y', 0), tr.get('m_LocalRotation', {}).get('z', 0), tr.get('m_LocalRotation', {}).get('w', 1)],
                        'color': d.get('m_Color', {}),
                        'intensity': d.get('m_Intensity', 1),
                        'range': d.get('m_Range', 10),
                        'shadows': d.get('m_Shadows', {}).get('m_Type', 0),
                    })

    # table mesh
    table_go = None
    for (cid, fid, d) in docs:
        if cid == 33 and d.get('m_Mesh', {}).get('guid') == '2c508133d66c13745835925286dfe1db':
            table_go = d.get('m_GameObject', {}).get('fileID')
    print('table mesh GO:', table_go)

    # ---- Scene Circuits.unity: Tabletop, Room Root, lights, camera ----
    path2 = os.path.join(UNITY_ROOT, 'Assets/Circuits/Scenes/Scene Circuits.unity')
    docs2, byname2 = docs_by_name(path2)
    for name, entries in byname2.items():
        for e in entries:
            tr = e['transform']
            if name in ('Tabletop', 'Room Root', 'Directional Light', 'Main Camera'):
                p = tr.get('m_LocalPosition', {})
                q = tr.get('m_LocalRotation', {})
                s = tr.get('m_LocalScale', {})
                print(f'{name}: pos=({p.get("x")},{p.get("y")},{p.get("z")}) rot=({q.get("x")},{q.get("y")},{q.get("z")},{q.get("w")}) scale=({s.get("x")},{s.get("y")},{s.get("z")})')

    with open(os.path.join(OUT, 'scene_lights.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print('lights:', json.dumps(result['lights'], ensure_ascii=False)[:800])

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""dump_glb.py — 解析 GLB JSON 块，打印节点树 + 网格图元统计（识别圆柱类引脚残留）。"""
import json, struct, sys

def load(path):
    with open(path, 'rb') as f:
        data = f.read()
    magic, ver, total = struct.unpack('<III', data[:12])
    assert magic == 0x46546C67, 'not GLB'
    off = 12
    doc = None
    while off < total:
        clen, ctype = struct.unpack('<II', data[off:off+8])
        chunk = data[off+8:off+8+clen]
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk)
        off += 8 + clen
    return doc

def mesh_dims(doc, mesh_idx, label):
    m = doc['meshes'][mesh_idx]
    prims = m.get('primitives', [])
    accs = doc['accessors']
    info = []
    for p in prims:
        pos = p.get('attributes', {}).get('POSITION')
        if pos is None:
            continue
        a = accs[pos]
        mn, mx = a.get('min'), a.get('max')
        if mn and mx:
            dims = [round(mx[i]-mn[i], 4) for i in range(3)]
            size = [round(v, 4) for v in mn + mx] if False else (round(mn[0],3), round(mn[1],3), round(mn[2],3), round(mx[0],3), round(mx[1],3), round(mx[2],3))
            info.append(f"dims={dims} ymin={round(mn[1],4)} tris~{a.get('count',0)//3}")
    print(f"  mesh[{mesh_idx}] '{m.get('name','?')}' prims={len(prims)}")
    for i in info:
        print(f"    {i}")

def walk(doc, idx=0, depth=0):
    nodes = doc['nodes']
    n = nodes[idx]
    name = n.get('name', f'node{idx}')
    mesh_idx = n.get('mesh')
    rot = n.get('rotation', '')
    scale = n.get('scale', '')
    extra = []
    if mesh_idx is not None:
        extra.append(f"mesh={mesh_idx}")
    if rot:
        extra.append(f"rot={rot}")
    if scale:
        extra.append(f"scale={scale}")
    print("  " * depth + f"- {name} {' '.join(extra)}")
    if mesh_idx is not None:
        mesh_dims(doc, mesh_idx, name)
    for c in n.get('children', []):
        walk(doc, c, depth + 1)

if __name__ == '__main__':
    path = sys.argv[1]
    doc = load(path)
    print(f"== {path.split('/')[-1]}")
    print(f"   nodes={len(doc['nodes'])} meshes={len(doc.get('meshes', []))} materials={len(doc.get('materials', []))}")
    scenes = doc.get('scenes', [{}])
    for root in scenes[0].get('nodes', []):
        walk(doc, root, 0)

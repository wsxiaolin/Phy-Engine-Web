#!/usr/bin/env python3
"""bbox_glb.py — 解析 GLB，计算每个节点世界空间包围盒（含 TRS 变换），识别退化/错位几何。"""
import json, struct, sys
import numpy as np

def load_glb(path):
    with open(path, 'rb') as f:
        data = f.read()
    magic, ver, total = struct.unpack('<III', data[:12])
    assert magic == 0x46546C67, 'not GLB'
    off = 12
    doc = binChunk = None
    while off < total:
        clen, ctype = struct.unpack('<II', data[off:off+8])
        chunk = data[off+8:off+8+clen]
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk)
        elif ctype == 0x004E4942:
            binChunk = chunk
        off += 8 + clen
    return doc, binChunk

def accessor_f32(doc, binData, acc_idx):
    a = doc['accessors'][acc_idx]
    bv = doc['bufferViews'][a['bufferView']]
    off = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    cnt, comp = a['count'], a['type']
    ncomp = {'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[comp]
    stride = bv.get('byteStride', 4*ncomp)
    out = np.empty((cnt, ncomp), dtype=np.float32)
    for i in range(cnt):
        out[i] = struct.unpack_from(f'<{ncomp}f', binData, off + i*stride)
    return out

def node_matrix(n):
    import math
    # glTF spec: node.matrix 优先（列主序 16 元素）；无 matrix 才走 TRS 分量。
    # 修复（2026-10-19）：旧版只解析 TRS 字段，忽略 matrix —— 提取器写入的
    # 全是 matrix 节点，被当成无变换，报出的"世界 bbox"实为局部顶点原值，
    # 曾误导裁决（Cylinder002 局部 ±0.0527 被当作 0.105m 巨物证据）。
    if 'matrix' in n:
        a = n['matrix']
        # 列主序 -> 行主序：M[r][c] = a[c*4+r]
        return np.array(a, dtype=np.float64).reshape(4, 4).T
    t = n.get('translation', [0,0,0]); r = n.get('rotation', [0,0,0,1]); s = n.get('scale', [1,1,1])
    x,y,z,w = r
    # quaternion -> matrix
    R = np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]], dtype=np.float64)
    M = np.eye(4)
    M[:3,:3] = R * np.array(s)
    M[:3,3] = t
    return M

def main(path):
    doc, binData = load_glb(path)
    nodes = doc['nodes']
    def world_bbox(idx, parent):
        n = nodes[idx]
        M = parent @ node_matrix(n)
        rows = []
        if 'mesh' in n:
            m = doc['meshes'][n['mesh']]
            for p in m.get('primitives', []):
                pos = p.get('attributes', {}).get('POSITION')
                if pos is None: continue
                v = accessor_f32(doc, binData, pos)
                vh = np.hstack([v, np.ones((len(v),1), dtype=np.float32)])
                w = (M @ vh.T).T[:, :3]
                rows.append(w)
        for c in n.get('children', []):
            sub = world_bbox(c, M)
            if sub is not None: rows.append(sub)
        if not rows: return None
        allv = np.vstack(rows)
        return allv.min(0), allv.max(0)

    print(f"== {path.split('/')[-1]}")
    for root in doc['scenes'][0]['nodes']:
        bb = world_bbox(root, np.eye(4))
        if bb is None:
            print(f"  node[{root}] {nodes[root].get('name','?')}: no geometry")
            continue
        mn, mx = bb
        dims = mx - mn
        print(f"  {nodes[root].get('name','?'):20} min={np.round(mn,4).tolist()} max={np.round(mx,4).tolist()} dims={np.round(dims,4).tolist()}")

if __name__ == '__main__':
    for p in sys.argv[1:]:
        main(p)

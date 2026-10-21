#!/usr/bin/env python3
"""pin_diag.py — 逐 mesh 节点世界 bbox（完整父链 + matrix/TRS 双语义），
诊断 Pin 网格错位。用法：python3 tools/pin_diag.py file.glb [...]"""
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
    if 'matrix' in n:
        # glTF 列主序 -> 行主序
        return np.array(n['matrix'], dtype=np.float64).reshape(4, 4).T
    t = n.get('translation', [0,0,0]); r = n.get('rotation', [0,0,0,1]); s = n.get('scale', [1,1,1])
    x,y,z,w = r
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
    def walk(idx, parent, depth):
        n = nodes[idx]
        M = parent @ node_matrix(n)
        if 'mesh' in n:
            rows = []
            m = doc['meshes'][n['mesh']]
            for p in m.get('primitives', []):
                pos = p.get('attributes', {}).get('POSITION')
                if pos is None: continue
                v = accessor_f32(doc, binData, pos)
                vh = np.hstack([v, np.ones((len(v),1), dtype=np.float32)])
                w = (M @ vh.T).T[:, :3]
                rows.append(w)
            if rows:
                allv = np.vstack(rows)
                mn, mx = allv.min(0), allv.max(0)
                ctr = (mn+mx)/2
                print(f"{'  '*depth}{n.get('name','?'):28s} ctr={np.round(ctr,4).tolist()} size={np.round(mx-mn,4).tolist()}")
        for c in n.get('children', []):
            walk(c, M, depth+1)
    print(f"== {path.split('/')[-1]}")
    for root in doc['scenes'][0]['nodes']:
        walk(root, np.eye(4), 0)

if __name__ == '__main__':
    for p in sys.argv[1:]:
        main(p)

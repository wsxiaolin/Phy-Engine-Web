#!/usr/bin/env python3
"""world_bbox.py — 从 GLB buffer 实算各 mesh 局部 bbox + 应用节点链世界变换后的 bbox。
用法: python3 tools/world_bbox.py <file.glb>
用途：诊断「漂浮小件 / 基座变薄 / 部件悬空」类几何错绑。"""
import json, struct, sys
sys.path.insert(0, os.path.dirname(__file__)) if (os := __import__('os')) else None
from dump_glb import load

import numpy as np

def mat_of(n):
    if 'matrix' in n:
        # glTF 列主序 -> 行主序
        return np.array(n['matrix'], dtype=np.float64).reshape(4,4).T
    t = n.get('translation', [0,0,0]); r = n.get('rotation', [0,0,0,1]); s = n.get('scale', [1,1,1])
    x,y,z,w = r
    # quaternion -> rotation matrix (column-major construction)
    R = np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w),   2*(x*z+y*w)],
        [2*(x*y+z*w),   1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w),   2*(y*z+x*w),   1-2*(x*x+y*y)],
    ])
    M = np.eye(4)
    M[:3,:3] = R * np.array(s)[None,:]
    M[:3,3] = t
    return M

def read_positions(doc, mesh_idx):
    m = doc['meshes'][mesh_idx]
    bvs = doc['bufferViews']; accs = doc['accessors']
    # binary chunk
    with open(sys.argv[1],'rb') as f:
        data = f.read()
    off = 12; bin_chunk = b''
    while off < len(data):
        clen, ctype = struct.unpack('<II', data[off:off+8])
        if ctype == 0x004E4942:
            bin_chunk = data[off+8:off+8+clen]
        off += 8 + clen
    out = []
    for p in m.get('primitives', []):
        pos = p['attributes']['POSITION']
        a = accs[pos]
        bv = bvs[a['bufferView']]
        start = bv.get('byteOffset',0) + a.get('byteOffset',0)
        cnt = a['count']
        stride = bv.get('byteStride', 12)
        vs = np.frombuffer(bin_chunk, dtype=np.float32, count=cnt*3, offset=start).reshape(cnt,3)
        if stride != 12:
            vs = np.stack([np.frombuffer(bin_chunk, dtype=np.float32, count=1, offset=start+i*stride+ k*4)[0] for i in range(cnt) for k in range(3)], axis=0).reshape(cnt,3)
        out.append(vs)
    return out

def main():
    doc = load(sys.argv[1])
    nodes = doc['nodes']
    world = {}
    def walk(idx, parent):
        M = parent @ mat_of(nodes[idx])
        world[idx] = M
        for c in nodes[idx].get('children', []):
            walk(c, M)
    walk(0, np.eye(4))
    def walk_print(idx, depth):
        n = nodes[idx]
        nm = n.get('name','?')
        mid = n.get('mesh')
        extra = ''
        if mid is not None:
            M = world[idx]
            allv = []
            for vs in read_positions(doc, mid):
                allv.append(vs)
            if allv:
                v = np.vstack(allv)
                # local bbox
                lmn, lmx = v.min(0), v.max(0)
                # world (affine, corner method fine for diag+rot; for sheared use full)
                vh = np.hstack([v, np.ones((len(v),1))]) @ M.T
                wmn, wmx = vh[:,:3].min(0), vh[:,:3].max(0)
                extra = (f' mesh={mid} local_dims={np.round(lmx-lmn,4).tolist()} '
                         f'world_dims={np.round(wmx-wmn,4).tolist()} '
                         f'world_min_y={wmn[1]:.4f}')
        print('  '*depth + f'- {nm}{extra}')
        for c in n.get('children', []):
            walk_print(c, depth+1)
    walk_print(0, 0)

if __name__ == '__main__':
    main()

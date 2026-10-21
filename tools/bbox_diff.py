#!/usr/bin/env python3
"""bbox_diff.py — Unity 期望世界 bbox (refdump slots×node.matrix) vs web GLB 实际 bbox。
用法: python3 tools/bbox_diff.py "Component Name"
逐 mesh 打印两侧 bbox 尺寸/位置差，定位提取器变换错绑。"""
import json, os, sys, struct
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, 'build', 'refdump')
GLB = os.path.join(ROOT, 'build', 'assets', 'components')


def glb_name(mid):
    return mid.replace(' ', '_').replace('-', '_')


def load_glb_doc(path):
    with open(path, 'rb') as f:
        data = f.read()
    json_len = struct.unpack('<I', data[12:16])[0]
    doc = json.loads(data[20:20 + json_len])
    bin_chunk = b''
    off = 20 + json_len
    while off < len(data):
        clen, ctype = struct.unpack('<II', data[off:off + 8])
        if ctype == 0x004E4942:
            bin_chunk = data[off + 8:off + 8 + clen]
        off += 8 + clen
    return doc, bin_chunk


def glb_positions(doc, bin_chunk, mesh_idx):
    m = doc['meshes'][mesh_idx]
    out = []
    for p in m.get('primitives', []):
        a = doc['accessors'][p['attributes']['POSITION']]
        bv = doc['bufferViews'][a['bufferView']]
        start = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
        cnt = a['count']
        vs = np.frombuffer(bin_chunk, dtype=np.float32, count=cnt * 3, offset=start).reshape(cnt, 3)
        out.append(vs)
    return np.vstack(out) if out else None


def mat_of(n):
    if 'matrix' in n:
        return np.array(n['matrix'], dtype=np.float64).reshape(4, 4).T  # col-major
    t = n.get('translation', [0, 0, 0]); r = n.get('rotation', [0, 0, 0, 1]); s = n.get('scale', [1, 1, 1])
    x, y, z, w = r
    R = np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w),   2*(x*z+y*w)],
        [2*(x*y+z*w),   1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w),   2*(y*z+x*w),   1-2*(x*x+y*y)],
    ])
    M = np.eye(4)
    M[:3, :3] = R * np.array(s)[None, :]
    M[:3, 3] = t
    return M


def bbox(v):
    mn, mx = v.min(0), v.max(0)
    return mn, mx, mx - mn


def main(mid):
    ref = json.load(open(os.path.join(REF, mid + '.json')))
    doc, bin_chunk = load_glb_doc(os.path.join(GLB, glb_name(mid) + '.glb'))

    # 期望：遍历 refdump 树
    exp = {}
    def walk_ref(idx):
        n = ref['nodes'][idx]
        M = np.array(n['matrix'], dtype=np.float64).reshape(4, 4).T
        for s in n.get('slots', []):
            p = np.array(s['positions'], dtype=np.float64).reshape(-1, 3)
            ph = np.hstack([p, np.ones((len(p), 1))]) @ M.T
            key = n['name']
            if key not in exp:
                exp[key] = ph[:, :3]
            else:
                exp[key] = np.vstack([exp[key], ph[:, :3]])
        for c in n.get('children', []):
            walk_ref(c)
    walk_ref(0)

    # 实际：GLB 世界
    act = {}
    def walk_glb(idx, parent):
        n = doc['nodes'][idx]
        M = parent @ mat_of(n)
        if n.get('mesh') is not None:
            v = glb_positions(doc, bin_chunk, n['mesh'])
            if v is not None:
                ph = np.hstack([v.astype(np.float64), np.ones((len(v), 1))]) @ M.T
                key = n.get('name', '?')
                act.setdefault(key, []).append(ph[:, :3])
        for c in n.get('children', []):
            walk_glb(c, M)
    walk_glb(0, np.eye(4))

    print(f'== {mid}: 期望(Unity) vs 实际(GLB) ==')
    allk = [k for k in exp if not str(k).lower().startswith('pin')]
    for k in allk:
        e = exp[k]
        emn, emx, ed = bbox(e)
        parts = act.get(k, [])
        if parts:
            a = np.vstack(parts)
            amn, amx, ad = bbox(a)
            print(f'  [{k}]')
            print(f'    exp: min={np.round(emn,4)} dims={np.round(ed,4)}')
            print(f'    act: min={np.round(amn,4)} dims={np.round(ad,4)}')
            print(f'    Δdims={np.round(ad-ed,4)} Δmin={np.round(amn-emn,4)}')
        else:
            print(f'  [{k}] exp-only(min={np.round(emn,4)} dims={np.round(ed,4)})  <<< GLB 缺失')
    for k in act:
        if k not in exp and not str(k).lower().startswith('pin'):
            a = np.vstack(act[k])
            amn, amx, ad = bbox(a)
            print(f'  [{k}] act-only(min={np.round(amn,4)} dims={np.round(ad,4)}) <<< 多出/改名')


if __name__ == '__main__':
    main(sys.argv[1])

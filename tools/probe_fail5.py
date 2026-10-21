#!/usr/bin/env python3
"""probe_fail5.py — FAIL 件几何对账探针（2026-10-21 重写）。

GLB 侧：解析 JSON+BIN，逐节点求世界矩阵链，对每个 mesh 的 POSITION
accessor 算局部 min/max，再仿射变换得世界 bbox。
参照侧：Unity 参照 dump（refdump，prefab/FBX 直读）nodes[].slots[].positions
本身已在世界空间，直接 min/max。
输出逐节点：GLB 世界 bbox vs 参照 bbox + 尺寸差比。

用法：
  python3 tools/probe_fail5.py [glb_dir] [ref_dir]
  glb_dir 默认 build/assets/components，ref_dir 默认 build/refdump
  指定元件子集：环境变量 FIVE="Air_Switch,Transformer"
"""
import json, struct, sys, os, math

GLB_DIR = sys.argv[1] if len(sys.argv) > 1 else 'build/assets/components'
REF_DIR = sys.argv[2] if len(sys.argv) > 2 else 'build/refdump'
ONLY = [s.strip() for s in os.environ.get('FIVE', '').split(',') if s.strip()]

# dump 文件名带空格（Unity ModelID）；按下划线去扩展名匹配
NAME_MAP = {f[:-5].replace(' ', '_'): f for f in os.listdir(REF_DIR) if f.endswith('.json')}


def _norm(s):
    return s.replace(' ', '_')


def load_glb(path):
    data = open(path, 'rb').read()
    magic, ver, total = struct.unpack('<III', data[:12])
    assert magic == 0x46546C67, 'not GLB'
    off, doc, bin_ = 12, None, b''
    while off < total:
        clen, ctype = struct.unpack('<II', data[off:off + 8])
        chunk = data[off + 8:off + 8 + clen]
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk)
        elif ctype == 0x004E4942:
            bin_ = chunk
        off += 8 + clen
    return doc, bin_


def node_mat(n):
    """glTF 节点局部矩阵（列主序 4x4 flat）。"""
    m = n.get('matrix')
    if m:
        return m
    # TRS → matrix（列主序）
    t = n.get('translation', [0, 0, 0])
    q = n.get('rotation', [0, 0, 0, 1])
    s = n.get('scale', [1, 1, 1])
    x, y, z, w = q
    m00 = 1 - 2 * (y * y + z * z); m01 = 2 * (x * y - z * w);     m02 = 2 * (x * z + y * w)
    m10 = 2 * (x * y + z * w);     m11 = 1 - 2 * (x * x + z * z); m12 = 2 * (y * z - x * w)
    m20 = 2 * (x * z - y * w);     m21 = 2 * (y * z + x * w);     m22 = 1 - 2 * (x * x + y * y)
    # 乘 scale（列）
    out = [m00 * s[0], m10 * s[0], m20 * s[0], 0,
           m01 * s[1], m11 * s[1], m21 * s[1], 0,
           m02 * s[2], m12 * s[2], m22 * s[2], 0,
           t[0], t[1], t[2], 1]
    return out


def mmul(a, b):
    """列主序 4x4：a·b。"""
    out = [0.0] * 16
    for i in range(4):
        for j in range(4):
            out[i * 4 + j] = sum(a[k * 4 + j] * b[i * 4 + k] for k in range(4))
    return out


def xform(m, p):
    x, y, z = p
    return (m[0] * x + m[4] * y + m[8] * z + m[12],
            m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14])


def bbox_of_points(pts):
    xs, ys, zs = pts[0::3], pts[1::3], pts[2::3]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def acc_points(doc, bin_, mesh):
    pts = []
    for prim in mesh['primitives']:
        a = doc['accessors'][prim['attributes']['POSITION']]
        bv = doc['bufferViews'][a['bufferView']]
        off = (bv.get('byteOffset', 0) + a.get('byteOffset', 0))
        n = a['count'] * 3
        # bufferView 可能有 stride（本管线无 stride，直接连读）
        vals = struct.unpack_from(f'<{n}f', bin_, off)
        pts.extend(vals)
    return pts


def walk_glb(doc, bin_, idx, parent, out):
    n = doc['nodes'][idx]
    wm = mmul(parent, node_mat(n))
    name = n.get('name', f'node{idx}')
    if n.get('mesh') is not None:
        pts = acc_points(doc, bin_, doc['meshes'][n['mesh']])
        if pts:
            local = bbox_of_points(pts)
            wp = [xform(wm, p) for p in zip(pts[0::3], pts[1::3], pts[2::3])]
            wmin, wmax = (min(p[0] for p in wp), min(p[1] for p in wp), min(p[2] for p in wp)), \
                         (max(p[0] for p in wp), max(p[1] for p in wp), max(p[2] for p in wp))
            out.append((name, len(pts) // 3, wmin, wmax))
    for c in n.get('children', []):
        walk_glb(doc, bin_, c, wm, out)


def fmt(b):
    return '[' + ', '.join(f'{v * 1000:.1f}' for v in b) + ']mm'


def dims(bmin, bmax):
    return tuple(bmax[i] - bmin[i] for i in range(3))


def compare(glb_path, ref_path):
    doc, bin_ = load_glb(glb_path)
    out = []
    scenes = doc['scenes'][doc.get('scene', 0)]['nodes']
    for s in scenes:
        walk_glb(doc, bin_, s, [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], out)
    ref = json.load(open(ref_path))
    refout = []
    # 修 2026-10-22：ref 侧原先直接拿 slots 顶点 min/max，但 slots 顶点是
    # 「父空间」（未乘本节点 matrix），GLB 侧却是世界 bbox——两侧不同空间，
    # 带旋转的节点（如底板轴变换）出现 X↔Y 互换伪影。现按 children 树把
    # 节点 matrix 链乘到世界，再算 bbox，与 GLB 侧同空间对账。
    all_children = set()
    for nd in ref['nodes']:
        all_children.update(nd.get('children') or [])
    roots = [i for i in range(len(ref['nodes'])) if i not in all_children]

    def ref_walk(i, parent_m):
        nd = ref['nodes'][i]
        wm = mmul(parent_m, nd.get('matrix') or [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
        allpts = []
        for slot in nd.get('slots', []):
            allpts.extend(slot['positions'])
        if allpts:
            wp = [xform(wm, p) for p in zip(allpts[0::3], allpts[1::3], allpts[2::3])]
            wmin, wmax = (min(p[0] for p in wp), min(p[1] for p in wp), min(p[2] for p in wp)), \
                         (max(p[0] for p in wp), max(p[1] for p in wp), max(p[2] for p in wp))
            refout.append((nd['name'], len(allpts) // 3, wmin, wmax))
        for c in nd.get('children') or []:
            ref_walk(c, wm)

    for r in roots:
        ref_walk(r, [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])

    print(f'==== {os.path.basename(glb_path)} ====')
    print(f'{"node":<22} {"GLB bbox(min)":<26} {"GLB bbox(max)":<26} {"dims(mm)":<22} {"ref dims(mm)":<22} ratio')
    refmap = {_norm(r[0]): r for r in refout}
    for name, nv, wmin, wmax in out:
        rd = refmap.get(_norm(name))
        d = dims(wmin, wmax)
        if rd:
            rdd = dims(rd[2], rd[3])
            ratio = '/'.join(f'{d[i] / rdd[i]:.2f}' if rdd[i] > 1e-9 else 'inf' for i in range(3))
            print(f'{name:<22} {fmt(wmin):<26} {fmt(wmax):<26} '
                  f'{fmt(d):<22} {fmt(rdd):<22} {ratio}')
        else:
            print(f'{name:<22} {fmt(wmin):<26} {fmt(wmax):<26} {fmt(d):<22} (ref: 无同名节点, verts={nv})')
    for name, nv, wmin, wmax in refout:
        if not any(_norm(o[0]) == _norm(name) for o in out):
            print(f'{name:<22} --- GLB 缺失 --- ref dims={fmt(dims(wmin, wmax))} verts={nv}')
    print()


def main():
    targets = ONLY or sorted(NAME_MAP.keys())
    for glb_name in targets:
        ref_name = NAME_MAP.get(glb_name)
        if not ref_name:
            print('MISS ref for', glb_name)
            continue
        glb_path = os.path.join(GLB_DIR, glb_name + '.glb')
        if not os.path.exists(glb_path):
            print('MISS glb', glb_path)
            continue
        compare(glb_path, os.path.join(REF_DIR, ref_name))


if __name__ == '__main__':
    main()

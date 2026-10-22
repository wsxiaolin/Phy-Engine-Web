#!/usr/bin/env python3
"""check_switch_pole.py — Simple Switch 拨杆数值不变量（提取非确定性防御）。

背景（2026-10-23 P2 非确定性观察）：跨会话两次提取同一 prefab，FBX 层给出的
Switch Pole / Pole 节点旋转列符号相反（欧拉读数层嫌疑，未定位根源），导致
YFLIP 修复结果掷骰子：上会话产物杆尖外翻 +0.147（=round-7 缺陷签名复现），
本会话产物杆尖 -0.0467 正确。本工具把「Unity 真值几何不变量」固化为硬断言，
提取/构建链跑它，符号再翻即报警非零退出，不再静默回归。

Unity 真值（unity prefab + 官方预览）：
  杆尖 x ≈ -0.044（内压向触点），枢轴端 x ≈ +0.05，底板边界 ±0.08。

用法: python3 tools/check_switch_pole.py [glb_path]
默认 glb_path = build/assets/components/Simple_Switch.glb
退出码: 0=不变量全部成立；1=违反（附数值）。
"""
import json, struct, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, 'build', 'components', 'Simple_Switch.glb')  # noqa: 旧路径占位


def load_glb(path):
    data = open(path, 'rb').read()
    if data[:4] != b'glTF':
        raise SystemExit(f'not a GLB: {path}')
    jl, bjl = struct.unpack('<II', data[12:20])
    return json.loads(data[20:20 + jl]), data, 20 + jl + 8


def read_positions(j, acc_i, data, binstart):
    a = j['accessors'][acc_i]
    bvo = j['bufferViews'][a['bufferView']].get('byteOffset', 0)
    off = binstart + bvo + a.get('byteOffset', 0)
    n = a['count']
    vals = struct.unpack('<%df' % (n * 3), data[off:off + n * 12])
    return [list(vals[i * 3:i * 3 + 3]) for i in range(n)]


def mv(m, v):
    return [m[0]*v[0] + m[4]*v[1] + m[8]*v[2] + m[12],
            m[1]*v[0] + m[5]*v[1] + m[9]*v[2] + m[13],
            m[2]*v[0] + m[6]*v[1] + m[10]*v[2] + m[14]]


def mm(a, b):
    o = [0.0] * 16
    for c in range(4):
        for r in range(4):
            o[c*4 + r] = sum(a[k*4 + r] * b[c*4 + k] for k in range(4))
    return o


def det3(m):
    c0, c1, c2 = m[0:3], m[4:7], m[8:11]
    cx = [c1[1]*c2[2] - c1[2]*c2[1], c1[2]*c2[0] - c1[0]*c2[2], c1[0]*c2[1] - c1[1]*c2[0]]
    return c0[0]*cx[0] + c0[1]*cx[1] + c0[2]*cx[2]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'assets', 'components', 'Simple_Switch.glb')
    j, data, binstart = load_glb(path)
    nodes = {n['name']: n for n in j['nodes'] if n.get('name')}
    need = ['X_MIRROR', 'Switch Pole', 'Pole']
    dan = [n for n in j['nodes'] if n.get('name', '').startswith('单刀')]
    if not all(k in nodes for k in need) or not dan:
        print('FAIL: node tree incomplete', file=sys.stderr)
        return 1
    chain = mm(mm(mm(nodes['X_MIRROR']['matrix'], dan[0]['matrix']),
                  nodes['Switch Pole']['matrix']), nodes['Pole']['matrix'])
    # Pole mesh 顶点
    pole_node = nodes['Pole']
    mesh_i = pole_node.get('mesh')
    if mesh_i is None:
        print('FAIL: Pole node has no mesh', file=sys.stderr)
        return 1
    p = j['meshes'][mesh_i]['primitives'][0]['attributes']['POSITION']
    pos = read_positions(j, p, data, binstart)
    pts = [mv(chain, v) for v in pos]
    xs = [q[0] for q in pts]
    world_det = det3(chain)
    xmin, xmax = min(xs), max(xs)
    ok = True
    # 不变量 1：杆尖内压（x_min ≈ -0.044，容差 ±0.025）
    if not (-0.069 <= xmin <= -0.019):
        print(f'FAIL invariant tip_x: xmin={xmin:.4f} expect≈-0.044 (±0.025)', file=sys.stderr)
        ok = False
    # 不变量 2：不越底板（xmax ≤ 0.08）
    if not (xmax <= 0.08):
        print(f'FAIL invariant plate: xmax={xmax:.4f} > 0.08 (外翻越界, round-7 签名)', file=sys.stderr)
        ok = False
    # 不变量 3：世界链 det>0（与 NODE_MESH_WINDING_FLIP 的翻转 winding 配对；
    # det<0 时 three.js 翻 frontFace，翻过的 winding 会内翻被剔除）
    if world_det <= 0:
        print(f'FAIL invariant world_det: {world_det:.3f} ≤0 (winding flip 配对失效)', file=sys.stderr)
        ok = False
    if ok:
        print(f'OK Simple Switch pole: x[{xmin:.4f},{xmax:.4f}] world_det={world_det:+.3f}')
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())

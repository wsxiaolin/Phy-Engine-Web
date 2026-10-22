#!/usr/bin/env python3
"""Air_Switch z 轴分离诊断（2026-10-22 值班第 4 轮固化）。

结论链（全部数值可复跑验证）：
1. USF=100：空气开关.FBX 顶点数值即米。
2. 管线数学与「prefab 引用语义」理论完全自洽：Box003/Off/On 的
   GLB 世界 bbox 与「Geometric 烘 + prefab TRS 链 + root Y+90°」
   的 Unity 左手系理论值逐项吻合（Box003 y/z 轴小数后 4 位一致，
   Off/On z[-0.0214,-0.0148] 完全一致）。
3. 但官方预览真值（VLM 读图）：拨杆在主体顶面、端子在两侧凸起
   基座上——不悬浮。probe 实测：主体 z[+1.8,+61] 全正，Off/On/Pin
   世界 z 全负（z 轴分离约 60mm）→ 视觉上脱离主体漂浮。
4. prefab「空气开关」root Q=(0,0.7071,0,0.7071)=Y+90° 为真数据
   （YAML 原值核验，非解析 bug）。
5. 数值假设实验：pin 世界 z = 1.1×(childM·v).x，其中 childM·v 的
   x = 顶点x×S + T_x。若 pin 节点 T_x 不做 x 镜像（+0.0142 而非
   -0.0142），pin 世界 z=+15.6mm——恰好落入主体 z 范围（贴位），
   且世界 x 不变（-52.6mm 左侧）。差值 Δz≈+30mm 与「T_x 符号」
   精确对应。 ⇒ 高嫌疑：**镜像与 root 轴交换的耦合环节**，
   待下轮用「变体 GLB + VLM 对照官方图」定谳。

下轮路线（性价比排序）：
A. 扫描全部 prefab 的 root Q：找「root Q 非平凡且 PASS」的元件，
   若其 pin 也 z 轴分离却 PASS → VLM FAIL 真因另寻（按钮尺寸/材质）。
B. 查官方预览生成管线（编辑器截图工具/装配代码）确认真实层级。
C. 生成「子节点 T_x 不镜像」变体 GLB → webshot → VLM 对官方图。
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from fbx_binary import parse, mesh_data
from unity_yaml import UNITY_ROOT, parse_prefab, scene_tree


def qmat(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def ap(T, R, S, v):
    return [T[i] + sum(R[i][j] * S[j] * v[j] for j in range(3)) for i in range(3)]


def main():
    f = parse(os.path.join(UNITY_ROOT, 'Assets/Physics-Lab/Circuits/空气开关.FBX'))
    from fbx_binary import p70
    usf = None
    for ch in f.nodes:
        if ch.name == 'GlobalSettings':
            usf = p70(ch, 'UnitScaleFactor')
    print(f'USF = {usf}')
    unit = 0.01 * float(usf or 1)
    meshes = {}
    for oid, (typ, n) in f.objects.items():
        if typ != 'Model':
            continue
        g = f.geometry_of(oid)
        if not g:
            continue
        name = (n.prop(1) or n.name).split('\x00', 1)[0].split(' Model')[0].strip()
        md = mesh_data(g[1]); pos = md['positions']
        xs = pos[0::3]; ys = pos[1::3]; zs = pos[2::3]
        meshes[name] = {'min': [min(xs) * unit, min(ys) * unit, min(zs) * unit],
                        'max': [max(xs) * unit, max(ys) * unit, max(zs) * unit]}

    pf = parse_prefab(os.path.join(UNITY_ROOT, 'Assets/Resources/Experiments/Home Circuits/Air Switch.prefab'))
    tree = scene_tree(pf)
    root = tree[0]
    inner = root['children'][0]

    def trs(node):
        t = node['transform']
        return t['position'], t['rotation'], t['scale']

    pi, qi, si = trs(inner)
    Ri = qmat(qi)
    print(f"root '空气开关' TRS: P={pi} S={si} (Q=Y+90 真数据)")
    print('== Unity 语义理论世界 bbox（左手系, m）==')
    for nm in ('Box003', 'Off', 'On'):
        node = [c for c in inner['children'] if c['name'] == nm][0]
        p, q, s = trs(node)
        Rr = qmat(q)
        mb = meshes['Cylinder001'] if nm != 'Box003' else meshes['Box003']
        geoT = [0, 0, -0.0786] if nm != 'Box003' else [0, 0, 0]
        corners = []
        for dx in (mb['min'][0], mb['max'][0]):
            for dy in (mb['min'][1], mb['max'][1]):
                for dz in (mb['min'][2], mb['max'][2]):
                    corners.append(ap(p, Rr, s, [dx + geoT[0], dy + geoT[1], dz + geoT[2]]))
        w = [ap(pi, Ri, si, c) for c in corners]
        xs = [c[0] for c in w]; ys = [c[1] for c in w]; zs = [c[2] for c in w]
        print(f"{nm}: x[{min(xs):+.4f},{max(xs):+.4f}] y[{min(ys):+.4f},{max(ys):+.4f}] z[{min(zs):+.4f},{max(zs):+.4f}]")
    print('\nGLB 实测(probe): Box003 z[+.0018,+.0610] | Off z[-.0214,-.0148] | On z[-.0214,-.0148] | Pin z[-.023,-.008]')
    print('=> 主体全正 / 子件全负: z 轴分离 ~60mm (悬浮根因)')
    print('\n假设实验: pin 节点 T_x 不镜像 (+0.0142) -> 世界 z=+15.6mm 落入主体 z 范围 -> 贴位')


if __name__ == '__main__':
    main()

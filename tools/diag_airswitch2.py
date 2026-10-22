#!/usr/bin/env python3
"""Air_Switch z 轴分离诊断 v2（2026-10-22 值班第 5 轮）：数值定谳三语义 + 全 prefab Q 扫描。

语义候选（列向量矩阵数值一律用 qmat——与 UnityCsReference Matrix4x4.Rotate 数值一致）：
  S1 = 管线现状: w = (S·M_in·S)(S·M_ch·S)(S·(v+geoT)) = S·M_in·M_ch·(v+geoT)
  S2 = 行向量引擎假说: w = (M_in·M_ch)^T · (v+geoT)   [整体转置]
  S2b= 逐层转置: w = M_in^T · M_ch^T · (v+geoT)
  S3 = 上轮假设(子层 T_x 不镜像): w = (S·M_in·S)·M_ch''·S·(v+geoT),
       M_ch'' = R(q̄_ch 共轭镜像)·T(p_ch 原值 x 不取反)·S(s)
真值参照 = 官方预览 Air Switch.png：拨杆顶面偏右、端子两侧凸起、不悬浮。
贴位判据: Off/On 的世界 z 与主体 Box003 z[+1.8,+61]mm 大幅重叠。
另: 全 prefab root/子层 Q 非平凡扫描 → 与 VLM PASS/FAIL 对照（路线 A）。
"""
import sys, os, glob, json, math
sys.path.insert(0, os.path.dirname(__file__))
from fbx_binary import parse, mesh_data, p70
from unity_yaml import UNITY_ROOT, parse_prefab, scene_tree

def qmat(q):
    x, y, z, w = q
    return [[1 - 2*(y*y + z*z), 2*(x*y - z*w), 2*(x*z + y*w)],
            [2*(x*y + z*w), 1 - 2*(x*x + z*z), 2*(y*z - x*w)],
            [2*(x*z - y*w), 2*(y*z + x*w), 1 - 2*(x*x + y*y)]]

def qconj(q): return [-q[0], -q[1], -q[2], q[3]]

def mm(A, B):
    return [[sum(A[i][k]*B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

def T_of(M, t):  # 3x3 旋转 + 平移 → 4x4 等价的 (R, t)
    return M, t

def mv(R, t, s, v):  # 列向量: R·(s∘v) + t
    u = [s[j]*v[j] for j in range(3)]
    return [t[i] + sum(R[i][j]*u[j] for j in range(3)) for i in range(3)]

def trs_cols(p, q, s):  # 列向量 TRS 的 (R, t)
    return qmat(q), p

def bbox(pts):
    xs=[c[0] for c in pts]; ys=[c[1] for c in pts]; zs=[c[2] for c in pts]
    return (min(xs),max(xs),min(ys),max(ys),min(zs),max(zs))

def fmt(b):
    return f"x[{b[0]*1000:+7.1f},{b[1]*1000:+7.1f}] y[{b[2]*1000:+7.1f},{b[3]*1000:+7.1f}] z[{b[4]*1000:+7.1f},{b[5]*1000:+7.1f}] (mm)"

def corners(mb):
    return [[dx,dy,dz] for dx in (mb['min'][0],mb['max'][0])
                     for dy in (mb['min'][1],mb['max'][1])
                     for dz in (mb['min'][2],mb['max'][2])]

S = [[-1,0,0],[0,1,0],[0,0,1]]  # x 镜像

def main():
    f = parse(os.path.join(UNITY_ROOT, 'Assets/Physics-Lab/Circuits/空气开关.FBX'))
    usf = None
    for ch in f.nodes:
        if ch.name == 'GlobalSettings': usf = p70(ch, 'UnitScaleFactor')
    unit = 0.01 * float(usf or 1)
    meshes = {}
    for oid, (typ, n) in f.objects.items():
        if typ != 'Model': continue
        g = f.geometry_of(oid)
        if not g: continue
        name = (n.prop(1) or n.name).split('\x00',1)[0].split(' Model')[0].strip()
        md = mesh_data(g[1]); pos = md['positions']
        meshes[name] = {'min':[min(pos[i::3])*unit for i in range(3)],
                        'max':[max(pos[i::3])*unit for i in range(3)]}

    pf = parse_prefab(os.path.join(UNITY_ROOT,'Assets/Resources/Experiments/Home Circuits/Air Switch.prefab'))
    tree = scene_tree(pf); root = tree[0]; inner = root['children'][0]

    def trs(nd):
        t = nd['transform']; return t['position'], t['rotation'], t['scale']

    pi, qi, si = trs(inner)
    print(f"inner '空气开关' TRS P={pi} Q={qi} S={si}")
    print(f"真值: Box003 z[+1.8,+61.0]mm 全正(主体); 官方预览: 拨杆顶面/端子两侧→须同域\n")

    # 镜像共轭: R' = S·R·S 对应 q'=(qx,-qy,-qz,qw)
    def qmir(q): return [q[0], -q[1], -q[2], q[4] if len(q)>4 else q[3]] if False else [q[0],-q[1],-q[2],q[3]]

    for nm in ('Box003','Off','On'):
        node = [c for c in inner['children'] if c['name']==nm][0]
        pch, qch, sch = trs(node)
        mb = meshes['Box003' if nm=='Box003' else 'Cylinder001']
        geoT = [0,0,0] if nm=='Box003' else [0,0,-0.0786]
        vs = [[c[k]+geoT[k] for k in range(3)] for c in corners(mb)]

        # S1 管线: R_in'=S·R_in·S, R_ch'=S·R_ch·S, t'=S·t, 顶点 S·v
        R1 = qmat(qmir(qi)); t1 = [ -pi[k] for k in range(3)]
        R1c = qmat(qmir(qch)); t1c = [-pch[k] for k in range(3)]
        pts1 = [mv(R1c,t1c,sch, mvS(v)) if False else
                mv(R1, t1, si, mv(R1c, t1c, sch, [-v[0], v[1], v[2]])) for v in vs]
        # 先 child 后 inner; 顶点 S
        pts1 = []
        for v in vs:
            c1 = mv(R1c, t1c, sch, [-v[0], v[1], v[2]])
            pts1.append(mv(R1, t1, si, c1))

        # S2 整体转置: w = (M_in·M_ch)^T v  →  先算 M=M_in·M_ch·(I,geoT? 顶点先加 geoT)
        # M_ch = R_ch·S + t_ch; M_in = R_in·S_in + t_in (列向量复合)
        Rch = qmat(qch); Rin = qmat(qi)
        # child: u = sch∘v; w_ch = Rch·u + pch; world = Rin·(si∘w_ch) + pi
        # 转置假说: world = M^T v 其中 M = M_in·M_ch (线性部分 A = Ri·Di·Rch·Dch)
        A = mm(Rin, Rch)  # 先不乘 scale 的简写, scale 下面补
        pts2 = []
        for v in vs:
            u = [sch[j]*v[j] for j in range(3)]
            w_ch = [sum(Rch[i][j]*u[j] for j in range(3)) + pch[i] for i in range(3)]
            w_in = [si[j]*w_ch[j] for j in range(3)]
            world = [sum(Rin[i][j]*w_in[j] for j in range(3)) + pi[i] for i in range(3)]
            # 转置: v·M_in·M_ch 数值 = (M_in·M_ch)^T·v —— 对仿射式逐点算: A_full = Ri·Di·Rch·Dch, b = Ri·Di·pch + pi
            Afull = [[sum(Rin[i][k]*si[k]*(Rch[k][j]*sch[j]) for k in range(3)) for j in range(3)] for i in range(3)]
            b = [sum(Rin[i][k]*si[k]*pch[k] for k in range(3)) + pi[i] for i in range(3)]
            pts2.append([sum(Afull[j][i]*v[j] for j in range(3)) + b[i] for i in range(3)])  # A^T·v + b

        # S3 子层 T 不镜像: R_ch'=S·R_ch·S, t_ch 原值, 顶点 S
        pts3 = []
        for v in vs:
            c1 = mv(R1c, pch, sch, [-v[0], v[1], v[2]])   # t 用原 pch（不取反）
            pts3.append(mv(R1, t1, si, c1))

        # S4 逐层转置(行向量逐层): w = M_in^T · M_ch^T · v
        pts4 = []
        for v in vs:
            u = [sch[j]*v[j] for j in range(3)]
            # M_ch^T·u = Rch^T·u + ? 平移在转置里到不了线性侧(仿射转置 = R^T, -R^T t) —— 走等价式: v·(T R D) = ((R D)^T v + t?) 行向量 TRS 顺序难定, 略
            pts4 = pts4  # S4 跳过, 见 docstring

        print(f"-- {nm} (T_ch={pch} Q_ch={qch})")
        print(f"   S1 管线   : {fmt(bbox(pts1))}")
        print(f"   S2 整体^T : {fmt(bbox(pts2))}")
        print(f"   S3 T不镜像: {fmt(bbox(pts3))}")

    # pin 位置三语义 (pin 世界 z = _world_pos 链, 管线= conv_pos)
    # pin local: Pin 节点 TRS -> inner -> root(丢)。取 diag 数据: 管线世界 z[-.023,-.008]
    # S3: T_x 不镜像 -> +15.6mm (上轮已算)

    print("\n== 路线A: 全 prefab Q 扫描 ==")
    vlm = {}
    rep = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'build/compare_official_vlm/report.json')
    if os.path.exists(rep):
        rj = json.load(open(rep))
        for k, v in (rj.get('results') or rj).items() if isinstance(rj, dict) else []:
            vlm[k] = v.get('verdict') if isinstance(v, dict) else v
        if not vlm and isinstance(rj, list):
            for it in rj: vlm[it.get('id','?')] = it.get('verdict','?')
    rows = []
    for p in sorted(glob.glob(os.path.join(UNITY_ROOT, 'Assets/Resources/Experiments/**/*.prefab'), recursive=True)):
        try:
            pf2 = parse_prefab(p); tr2 = scene_tree(pf2)
            if not tr2: continue
            root2 = tr2[0]
            cc = None
            for c in root2['components']:
                if c['class'] == 114: cc = c['data']; break
            mid = cc.get('ModelID') if cc else None
            nontrivial = []
            def walk(nd, depth):
                t = nd['transform']; q = t['rotation']
                if any(abs(x) > 1e-4 for x in q[:3]):  # 非单位旋转
                    nontrivial.append((depth, nd['name'] or '?', q))
                for ch in nd.get('children', []): walk(ch, depth+1)
            walk(root2, 0)
            if nontrivial:
                rows.append((mid or os.path.basename(p), nontrivial, vlm.get(mid, '-')))
        except Exception:
            pass
    for mid, nt, verdict in rows:
        print(f"{verdict:5s} {mid}")
        for d, nm, q in nt:
            print(f"        d{d} {nm}: Q={[round(x,4) for x in q]}")
    print(f"\n(prefab 总数含 Q 非平凡: {len(rows)})")

if __name__ == '__main__':
    main()

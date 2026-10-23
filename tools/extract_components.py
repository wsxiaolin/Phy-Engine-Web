#!/usr/bin/env python3
"""Extract Unity circuit component prefabs into glTF GLB + catalog.json.

Coordinate system note:
  Unity is left-handed Y-up; three.js/glTF is right-handed Y-up.
  We mirror X on export (x -> -x) and flip triangle winding accordingly.
  FBX raw vertices are converted to meters via UnitScaleFactor (FBX base = cm).
  UV v is flipped (Unity bottom-left origin -> glTF top-left).
"""
import os, sys, json, math, struct
sys.path.insert(0, os.path.dirname(__file__))
from unity_yaml import (UnityAssets, parse_prefab, scene_tree, parse_material,
                        UNITY_ROOT, load_yaml_docs, safe_name, fbx_meta_mesh_names)
from fbx_binary import parse as fbx_parse, mesh_data, p70, p70v3

OUT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'build', 'assets'))
MIRROR_X = True
# 烘焙开关：1 = 把 FBX 内部 Model 链世界矩阵烘进顶点（1482c4d 起的旧行为）；
# 0 = 顶点保持 Model 局部空间，prefab 节点 TRS 承担全部变换（Unity 导入语义）。
# 2026-10-19 定谳：默认改 0。官方预览（unity/.../Previews/Circuits，真 ground truth）
# A/B 裁决 Rectifier/Transformer——baked FAIL（整流器被压扁/变压器变细长条），
# nobake 双双 PASS；1482c4d 的 bake 与 .meta 权威映射同批引入，.meta 修复了
# 19.3m 芯片巨物（保留），bake 则是回归源。需要旧行为时 BAKE_FBX_M=1。
BAKE_FBX_M = os.environ.get('BAKE_FBX_M', '0') != '0'
# Pin mesh 保留开关：默认 1 = 保留 FBX 内 Pin 网格（Unity 真身为大六角螺母
# 香蕉插座，见 Previews/Circuits/Yes-Gate.png）。矩阵双 bug 修复 + nobake 后
# 「Pin 烘焙错位飘到场外」的前提已不成立。
# 2026-10-22 晚 A/B 裁决（5 FAIL 件定向 KEEP_PIN=1 重提取→官方预览 VLM）：
# Basic_Inductor/Simple_Switch（镜像链真回归）+ Logic_Output（基线存量 FAIL）
# 三件全部转 PASS，0 件转坏；前端 components.js glbHasPinMesh 检测（/^pin/i，
# 与 is_pin_node 同源）保证 GLB 带 pin 网格时自动跳过程序化柱，无双柱渲染。
# 结论：真身 pin 网格优于程序化柱，默认翻 1；程序化柱仅作无 pin FBX 兜底。
# 全量回归终态（36 件官方对照）：35 PASS/1 FAIL，唯一 FAIL=Simple_Switch
# （复判 2PASS/3FAIL 多数决，见 compare_official_vlm/Simple_Switch.json notes）。
KEEP_PIN_MESHES = os.environ.get('KEEP_PIN_MESHES', '1') != '0'

# 2026-10-23 P0 终版：Simple Switch 拨杆镜像失配定点修复（36 件最后一件 FAIL）。
# 根因三层（前两轮 round-8 pure / round-9 Rz180 的教训沉淀）：
#   ① s3gen 镜像语义 = 顶层 X_MIRROR(det-1) + 仅平移 T_x 镜像、旋转列不镜像
#     → Switch Pole 世界帧 XM·SP 与 Unity 真值 Msw 相比本地 y 轴被净翻转
#     （对称件不可见；拨杆不对称 → 杆尖 +0.147 外翻越界，round-7 起已知缺陷）。
#   ② web/src/app.js syncPole() 每次 instantiate 强设 Pole 节点 rotation.x
#     =0.79(翘起)/0(压平)——提取器给 Pole 写的任何旋转都会被运行时覆写，
#     round-9 的 Pole 节点 Rz180 前乘因此机制性无效（覆写后杆穿到桌面下）。
#   ③ 纯旋转 det+1 永远补不了 X_MIRROR 的 det-1，需要的反射只能放在 app
#     不覆写的节点上 → Switch Pole（纯 frame 节点、无 mesh、独子=Pole）。
# 修复 = Switch Pole 本地矩阵后乘 diag(1,-1,1)（列主序 flat 即 col1 取负）：
#   修复后 XM·SP·Sy ≡ Msw（与 prefab TRS 数值恒等：quat±0.5/scale(1.2,1.4,1.2)
#   /pos(0.05,0.0315,-0.01)）；Pole 节点保持 Unity 原生 Rx(45°)（HEAD/pure
#   逐位一致），app 覆写 rotation.x→0.79 后世界矩阵 = Msw·Rx(0.79)，与 round-8
#   pure 实验 VLM-PASS 姿态精确复现（杆尖 x=-0.041 内压触点、枢轴 +0.05）。
#   （上会话勘误：L52-54 原 det 推理有误，见下方 NODE_MESH_WINDING_FLIP 注释）
#   闭合态(rotation.x=0)：杆沿 SP 本地 y 平躺 x∈[-0.08,+0.05] 压住触点 ✓。
# 验证配方：重提取后 live 探针（playwright evaluate: getObjectByName('Pole')
#   .matrixWorld，期望 cols ≈ [(0,0,-1.2),(-0.985,+0.852,0),(0.994,+0.845,0)]
#   +t(0.05,0.8115,-0.01)@桌面0.78）+ shot_pairs/compose_official/
#   vlm_review_official 三连（Simple Switch 单件）。
NODE_LOCAL_YFLIP = {('Simple Switch', 'Switch Pole')}

# 2026-10-23 P0：NODE_SKIP_FBX_M —— 跳过 fbx_M 烘焙（双重变换）。
# Relay Component/底板：diag_transform 实锤其 Model 的 world_M 含 S=1.2268+轴交换，
# 与 prefab 节点 TRS 的 S=1.2268 完全一致（Unity 导入 FBX 时 Model 变换已体现在
# prefab 层级），提取器再烘 fbx_M = scale 应用两次+多转一次，底板变 ±0.12m 大薄板
# 盖掉台阶底座（VLM FAIL 根因）。Unity 语义 = world_M × vertex × unit，不烘。
NODE_SKIP_FBX_M = {('Relay Component', '底板')}

# 2026-10-23 P0b 勘误+修复：YFLIP 上轮 VLM FAIL「拨杆完全消失」的机理。
# 原推理（已删）「总 det=(-1)·(-2.016)·(+1)=+2.016>0 不翻 frontFace」错把
# Switch Pole 本地 det 当世界链 det。GLB dump 实测（列主序）：
#   YFLIP 后 Switch Pole 本地 det=+2.016；世界链 = X_MIRROR(-1)×单刀(+1)×
#   (+2.016)×Pole(+1) = -2.016 <0 → three.js 翻 frontFace；
#   HEAD（YFLIP 前）本地 det=-2.016 → 世界 +2.016 >0 → 不翻 frontFace，
#   Pole mesh 原始 winding 恰好正确（HEAD 下拨杆一直可见、仅方向错）。
# YFLIP 翻世界 det 符号 → frontFace 行为反转 → 原始 winding 变内翻 →
# 剔除 → VLM 判「拨杆消失」。修复 = 对该 mesh 同步翻 winding（fan 三角
# [a,b,c]→[a,c,b]）；法线弃原始值改 _face_normals 从翻后 indices 重算
# （与剔除方向严格自洽；平滑度损失由 VLM 裁决）。不改 md（fbx_cache 复用
# 安全），仅在 _emit_mesh 局部 groups 层翻转。
NODE_MESH_WINDING_FLIP = {('Simple Switch', 'Pole')}

# Geometric 烘焙（2026-10-21 收敛为默认全量）：
# 背景——FBX Model 的 GeometricTranslation/Rotation/Scaling 是「几何相对节点」
# 的变换，Unity 导入时会烘进 Mesh 资产顶点。此前管线漏烘，导致「世界坐标+
# pivot」型导出的几何带着世界偏移和 Z-up 姿态直接挂到 prefab 节点 TRS 上，
# 渲染成漂浮/错位/沉地板/部件横躺。
# 数值实证（Yes-Gate，10-20）：pin raw + GeometricM 后柱体以原点为中心立于
# y=0，经 prefab TRS 世界 bbox 与官方预览锚点精确吻合（柱心 x=±0.06、柱底
# y=20mm=底板顶 19.9mm）。
# 为何默认全量（10-21 推翻 10-20 白名单结论）——权威审计
# （build/audit_geometric3.txt，.meta fileIDToRecycleName 对齐）发现：
# - 6 个 FAIL 件的病灶 mesh 全部带非平凡 Geometric：LED屏幕.FBX（T 大偏移+
#   R=-90，prefab S=3 放大成 1.9m 位移=「显示屏悬空」）、开关.FBX 按钮三个
#   Model（R=-90=「按钮扁片」）、电容.FBX:Cylinder002（R=(90,-79,0.86)=「蓝
#   圆筒错位」）、互感器.FBX（T=22.75=IC 偏移）。
# - 「拷贝模式 raw 即对位」旧理论不成立：拷贝的 TRS=LclTRS 不含 Geometric，
#   Unity 顶点恒为 raw×GeometricM×节点链，两种模式都必须烘。
# - 旧「全量烘 LED 横躺」实证实为当时 swap(x,z,y) 实现 bug 的产物（docstring
#   已记录），不是「不该烘」的证据。
# - 已 PASS 件不受影响的机理：多数引用 Geometric 平凡；或 prefab S≈0.001 把
#   偏移缩到亚毫米（集成电路模块.FBX geoT=23.5mm×0.001=0.02mm）。
# 回退：GEOMETRIC_BAKE_FBXS='基础件.FBX' 恢复白名单；'none' 全关。
GEOMETRIC_BAKE_FBXS = [s.strip() for s in
                       os.environ.get('GEOMETRIC_BAKE_FBXS', '*').split(',')
                       if s.strip() and s.strip().lower() != 'none']
_GEOMETRIC_BAKE_ALL = '*' in GEOMETRIC_BAKE_FBXS

# CircuitComponent MonoBehaviour fields we need
def quatch(t):
    return t

def qmul(a, b):
    """Hamilton product, (x,y,z,w)."""
    ax, ay, az, aw = a; bx, by, bz, bw = b
    return [
        aw*bx + ax*bw + ay*bz - az*by,
        aw*by - ax*bz + ay*bw + az*bx,
        aw*bz + ax*by - ay*bx + az*bw,
        aw*bw - ax*bx - ay*by - az*bz,
    ]

def qrot(q, v):
    """Rotate vector v by quaternion q."""
    x, y, z = v
    qx, qy, qz, qw = q
    # v' = q * v * q^-1
    t = [qw*x + qy*z - qz*y, qw*y + qz*x - qx*z, qw*z + qx*y - qy*x]
    return [x + 2*(qy*t[2]-qz*t[1]), y + 2*(qz*t[0]-qx*t[2]), z + 2*(qx*t[1]-qy*t[0])]

def trs_apply(t, p):
    """Apply node TRS to a point (node local -> parent)."""
    s = t['scale']
    q = t['rotation']
    v = [p[0]*s[0], p[1]*s[1], p[2]*s[2]]
    v = qrot(q, v)
    return [v[0]+t['position'][0], v[1]+t['position'][1], v[2]+t['position'][2]]

def q_conj(q):
    return [-q[0], -q[1], -q[2], q[3]]

def q_mirror_x(q):
    """Quaternion transform under reflection S = diag(-1,1,1): R' = S R S.
    For q=(x,y,z,w): S R S = R(-theta, S*u)  =>  q' = (w, -S*v) in (w,v) form
    => in Unity (x,y,z,w) order: (x, -y, -z, w).
    Verified: +90deg around Y (0,.707,0,.707) -> (0,-.707,0,.707) = -90 around Y."""
    return [q[0], -q[1], -q[2], q[3]]

def q_mirror_x_v2(q):
    # R' = S R S  =>  q' = (w, S^-1 applied?) — compute directly:
    # S R S with S=diag(-1,1,1): for quaternion (w, v): q' = (w, S v)? No:
    # S R(a,u) S = R(a, S u)? Rotations conjugated by reflection: R' = R(-a, S u)?
    # Empirical: mirror quaternion (x,y,z,w) -> (-x, y, z, -w)?? We test at runtime.
    return [-q[0], q[1], q[2], -q[3]]


class GLB:
    def __init__(self):
        self.bin = bytearray()
        self.json = {'asset': {'version': '2.0', 'generator': 'plw-extract'},
                     'scenes': [{'nodes': [0]}], 'scene': 0,
                     'nodes': [], 'meshes': [], 'materials': [], 'accessors': [],
                     'bufferViews': [], 'buffers': [{'byteLength': 0}]}
        self.tex_cache = {}   # (source path) -> index
        self.images = []
        self.samplers = []
        self.textures = []

    def _pad(self):
        while len(self.bin) % 4:
            self.bin.append(0)

    def _bview(self, data, target=34962):
        self._pad()
        off = len(self.bin)
        self.bin.extend(data)
        return {'buffer': 0, 'byteOffset': off, 'byteLength': len(data), 'target': target}

    def accessor(self, arr, comp, ty='VEC3', normalized=False):
        data = struct.pack(f'<{len(arr)}{comp}', *arr)
        bv = self._bview(data)
        cnt = len(arr) // {'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'SCALAR': 1}[ty]
        idx = len(self.json['accessors'])
        mn = min(arr); mx = max(arr)
        self.json['accessors'].append({'bufferView': len(self.json['bufferViews']),
                                       'componentType': {'f': 5126, 'H': 5123, 'I': 5125, 'B': 5121}[comp],
                                       'count': cnt, 'type': ty,
                                       'min': [mn], 'max': [mx]} if ty == 'SCALAR' else
                                      {'bufferView': len(self.json['bufferViews']),
                                       'componentType': 5126, 'count': cnt, 'type': ty})
        self.json['bufferViews'].append(bv)
        return idx

    def add_mesh(self, name, positions, normals, uvs, indices, matidx=None, morph=False):
        prim = {}
        prim['attributes'] = {'POSITION': self.accessor(positions, 'f', 'VEC3'),
                              'NORMAL': self.accessor(normals, 'f', 'VEC3')}
        if uvs:
            prim['attributes']['TEXCOORD_0'] = self.accessor(uvs, 'f', 'VEC2')
        comp = 'H' if max(indices) < 65536 else 'I'
        if comp == 'H':
            data = struct.pack(f'<{len(indices)}H', *indices)
            bvt = 34963
            self._pad()
            off = len(self.bin); self.bin.extend(data)
            self.json['bufferViews'].append({'buffer': 0, 'byteOffset': off, 'byteLength': len(data), 'target': bvt})
            self.json['accessors'].append({'bufferView': len(self.json['bufferViews']) - 1, 'componentType': 5123,
                                           'count': len(indices), 'type': 'SCALAR', 'min': [min(indices)], 'max': [max(indices)]})
            prim['indices'] = len(self.json['accessors']) - 1
        else:
            prim['indices'] = self.accessor(indices, 'I', 'SCALAR')
        if matidx is not None:
            prim['material'] = matidx
        mi = len(self.json['meshes'])
        self.json['meshes'].append({'name': name, 'primitives': [prim]})
        return mi

    def add_mesh_multi(self, name, prims):
        """prims: list of dicts {positions, normals, uvs, indices, matidx}.
        One glTF mesh with one primitive per material slot (Unity submesh parity)."""
        out_prims = []
        for p in prims:
            prim = {}
            prim['attributes'] = {'POSITION': self.accessor(p['positions'], 'f', 'VEC3'),
                                  'NORMAL': self.accessor(p['normals'], 'f', 'VEC3')}
            if p.get('uvs'):
                prim['attributes']['TEXCOORD_0'] = self.accessor(p['uvs'], 'f', 'VEC2')
            indices = p['indices']
            comp = 'H' if max(indices) < 65536 else 'I'
            if comp == 'H':
                data = struct.pack(f'<{len(indices)}H', *indices)
                bvt = 34963
                self._pad()
                off = len(self.bin); self.bin.extend(data)
                self.json['bufferViews'].append({'buffer': 0, 'byteOffset': off, 'byteLength': len(data), 'target': bvt})
                self.json['accessors'].append({'bufferView': len(self.json['bufferViews']) - 1, 'componentType': 5123,
                                               'count': len(indices), 'type': 'SCALAR', 'min': [min(indices)], 'max': [max(indices)]})
                prim['indices'] = len(self.json['accessors']) - 1
            else:
                prim['indices'] = self.accessor(indices, 'I', 'SCALAR')
            if p.get('matidx') is not None:
                prim['material'] = p['matidx']
            out_prims.append(prim)
        mi = len(self.json['meshes'])
        self.json['meshes'].append({'name': name, 'primitives': out_prims})
        return mi

    def add_material(self, mat):  # mat: parsed .mat dict with resolved texture path
        m = {'name': mat.get('name', 'mat'),
             'pbrMetallicRoughness': {'baseColorFactor': _srgb_color(mat.get('color') or [1,1,1,1])}}
        mr = m['pbrMetallicRoughness']
        if mat.get('maintex_path'):
            ti = self._texture(mat['maintex_path'])
            mr['baseColorTexture'] = {'index': ti}
        if mat.get('metallic') is not None:
            mr['metallicFactor'] = mat['metallic']
        else:
            mr['metallicFactor'] = 0.0
        sm = mat.get('smoothness')
        mr['roughnessFactor'] = max(0.05, 1.0 - (sm if sm is not None else 0.3))
        emis = mat.get('emissionColor')
        if emis and (emis[0] or emis[1] or emis[2]):
            m['emissiveFactor'] = [min(1.0, emis[0]), min(1.0, emis[1]), min(1.0, emis[2])]
        if mat.get('mode') in ('fade', 'transparent'):
            m['alphaMode'] = 'BLEND'
            mr['baseColorFactor'][3] = (mat.get('color') or [1,1,1,1])[3]
        elif mat.get('mode') == 'cutout':
            m['alphaMode'] = 'MASK'
        idx = len(self.json['materials'])
        self.json['materials'].append(m)
        return idx

    def _texture(self, path):
        key = path
        if key in self.tex_cache:
            return self.tex_cache[key]
        ext = os.path.splitext(path)[1].lower()
        mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg'}.get(ext[1:], 'image/png')
        with open(os.path.join(UNITY_ROOT, path), 'rb') as f:
            data = f.read()
        self._pad()
        off = len(self.bin)
        self.bin.extend(data)
        ii = len(self.json.get('images', []))
        self.json.setdefault('images', []).append({'bufferView': len(self.json['bufferViews']),
                                                   'mimeType': mime})
        self.json['bufferViews'].append({'buffer': 0, 'byteOffset': off, 'byteLength': len(data)})
        si = len(self.json.get('samplers', []))
        self.json.setdefault('samplers', []).append({'magFilter': 9729, 'minFilter': 9987,
                                                     'wrapS': 10497, 'wrapT': 10497})
        ti = len(self.json.get('textures', []))
        self.json.setdefault('textures', []).append({'sampler': si, 'source': ii})
        self.tex_cache[key] = ti
        return ti

    def add_node(self, name, mesh=None, children=None, matrix=None):
        n = {'name': name}
        if mesh is not None: n['mesh'] = mesh
        if children: n['children'] = children
        if matrix: n['matrix'] = matrix
        idx = len(self.json['nodes'])
        self.json['nodes'].append(n)
        return idx

    def write(self, path):
        # Scene roots = every node not referenced as a child. Components emit a
        # single root; multi-part assets (e.g. room.glb) emit several.
        referenced = set()
        for n in self.json['nodes']:
            referenced.update(n.get('children', []))
        self.json['scenes'][0]['nodes'] = [i for i in range(len(self.json['nodes'])) if i not in referenced]
        self.json['buffers'][0]['byteLength'] = len(self.bin)
        js = json.dumps(self.json, separators=(',', ':')).encode('utf-8')
        while len(js) % 4:
            js += b' '
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        with open(path, 'wb') as f:
            f.write(b'glTF' + struct.pack('<II', 2, total))
            f.write(struct.pack('<II', len(js), 0x4E4F534A))
            f.write(js)
            f.write(struct.pack('<II', len(self.bin), 0x004E4942))
            f.write(self.bin)
        return total


def _srgb_color(c):
    def lin(x):
        x = max(0.0, min(1.0, x))
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    return [lin(c[0]), lin(c[1]), lin(c[2]), c[3]]



def euler_to_quat(rx, ry, rz):
    """Euler XYZ(deg) -> quaternion (x,y,z,w). Unity 左手系。"""
    import math as _m
    cx, sx = _m.cos(_m.radians(rx/2)), _m.sin(_m.radians(rx/2))
    cy, sy = _m.cos(_m.radians(ry/2)), _m.sin(_m.radians(ry/2))
    cz, sz = _m.cos(_m.radians(rz/2)), _m.sin(_m.radians(rz/2))
    return [
        sx*cy*cz + cx*sy*sz,
        cx*sy*cz - sx*cy*sz,
        cx*cy*sz + sx*sy*cz,
        cx*cy*cz - sx*sy*sz,
    ]

# 2026-10-22 镜像语义统一修复（Air_Switch 拨杆倒挂定谳，diag_airswitch2.py 可复跑）：
#   旧管线 = 每层 S·M·S 共轭 + 顶点 S —— 数学自洽，但子层平移被镜像进旋转父帧，
#   Air_Switch 拨杆 y[-86,-73] 倒挂桌面下（官方预览三特征全部矛盾）。
#   新语义 = R 不共轭（q 原样）+ 顶点不镜像 + 顶层一次 S（场景根 X_MIRROR 包装节点）。
#   平移镜像按变体（两者与 S3 锚点数值恒等，Air_Switch p_in=0）：
#     s3gen（默认）= 深度≥2 节点 T_x 镜像；深度1（top_level）不镜像
#       —— 单层布局（房间/芯片叶节点）与旧管线渲染完全一致，回归面最小。
#     unified = 每层 T_x 镜像（快照公式原样；t1≠0 的 ~26 个非 pin root-child 有差）。
#   pins（catalog _world_pos）不动：prefab 内作者摆放位置 = Unity 渲染真值，旧公式已正确。
#   winding 不再翻转：three.js r169 对 matrixWorld.det<0 自动反转剔除方向
#   （frontFaceCW），X_MIRROR 包装节点已承担这一次翻转；旧管线的翻转
#   配平对象是「顶点镜像+det+1 节点」，新语义下保留即双重翻转=内翻。
#   数值锚点：Air_Switch 拨杆(Off/On 圆柱) 修复后 z[+14.6,+21.2]mm y[+73,+86]mm=顶面。
MIRROR_FIX = os.environ.get('MIRROR_FIX', 's3gen')  # s3gen | unified

def trs_matrix(t, mirror_x=MIRROR_X, unit=1.0, top_level=False):
    """Node local matrix (2026-10-22 统一镜像语义，见上方块注释)。"""
    q = t['rotation']; p = t['position']; s = t['scale']
    q2 = q  # R 不共轭：镜像统一交给顶层 X_MIRROR 包装节点
    if mirror_x and MIRROR_FIX == 's3gen' and top_level:
        mirror_t = False   # s3gen：深度1 平移不镜像（单层布局与旧管线一致）
    else:
        mirror_t = bool(mirror_x)
    if mirror_t:
        p = [-p[0]*unit, p[1]*unit, p[2]*unit]
    else:
        p = [p[0]*unit, p[1]*unit, p[2]*unit]
    # quaternion to matrix：flat 布局 = 列主序（glTF matrix 字段 / three.js elements 同序）。
    # 上面 m 的四元数部分恰好按「数学矩阵的列」分组写入（m[0..2]=R 第0列…），
    # 与 glTF 列主序规范一致——此部分一直是对的。
    x, y, z, w = q2
    m = [1-2*(y*y+z*z), 2*(x*y+z*w), 2*(x*z-y*w), 0.0,
         2*(x*y-z*w), 1-2*(x*x+z*z), 2*(y*z+x*w), 0.0,
         2*(x*z+y*w), 2*(y*z-x*w), 1-2*(x*x+y*y), 0.0,
         p[0], p[1], p[2], 1.0]
    # apply scale：R·S 语义 = 数学矩阵「列 j」整体 × s[j]（Unity TRS 先缩放后旋转）。
    # 列主序 flat 下列 j 的三个元素是 m[j*4+0..2]。
    # 2026-10-19 修复记录：旧版按行主序下标 m[i*4+c]×=s[c] 相乘，等于把缩放挂到
    # diag(s)·R（父轴缩放、错误一侧）——非均匀缩放+旋转共存的节点（门电路
    # Icon/Output/Input 面片 scale=(0.03,0.0024,1.0)+rot 90°X）y/z 挂反成 1m 巨物；
    # 纯平移/均匀缩放节点不受影响，且 refdump 与提取同错导致数值审计无法发现
    # （同源盲区），直到官方预览对照（Previews/Circuits 真基准）才暴露。
    # 同日第二次修复：曾试图整体转置数组补救——但转置会把平移转到底行（行向量
    # 约定，glTF 读成零平移）且旋转被求逆（Rᵀ）。正确做法只改本循环。
    for j in range(3):
        for r in range(3):
            m[j*4+r] *= s[j]
    return m


def conv_pos(v, unit, mirror_x=MIRROR_X):
    # 2026-10-22：网格路径传 mirror_x=False（顶点不镜像）；pin 路径保留默认镜像（真值）。
    p = [v[0]*unit, v[1]*unit, v[2]*unit]
    if mirror_x: p[0] = -p[0]
    return p

def conv_normal(v, mirror_x=MIRROR_X):
    if mirror_x: return [-v[0], v[1], v[2]]
    return list(v)

def flip_winding(indices):
    # reverse each triangle
    out = []
    for i in range(0, len(indices), 3):
        out.extend([indices[i+2], indices[i+1], indices[i]])
    return out


def _p3(n, name, default):
    """p70 归一化为 3-list：部分 FBX 的 P 条目值结构不同（返回 float/None）。"""
    v = p70(n, name)
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        return [float(v[0]), float(v[1]), float(v[2])]
    if isinstance(v, (int, float)):
        return [float(v)] * 3
    return default


def _fbx_trs_matrix(oid, f):
    """Model 节点的局部 TRS 4x4（行主序，FBX 原始单位，T 不乘 unit）。"""
    n = f.objects[oid][1]
    t = _p3(n, 'Lcl Translation', [0, 0, 0])
    r = _p3(n, 'Lcl Rotation', [0, 0, 0])
    s = _p3(n, 'Lcl Scaling', [1, 1, 1])
    q = euler_to_quat(*r)
    return trs_matrix({'position': t, 'rotation': q, 'scale': s})


def _mmul(A, B):
    """4x4 矩阵相乘，A·B（列主序 flat，与 glTF/three.js 一致；先施 B 再施 A）。
    2026-10-19 修复记录：旧版按行主序下标相乘，在列主序 flat 上等价于算出 B·A
    （乘序颠倒）。BAKE_FBX_M 烘焙路径的失败是双 bug 叠加：本乘序颠倒 +
    trs_matrix 缩放挂错侧（diag(s)·R 而非 R·diag(s)），官方预览 A/B 裁决的
    「Rectifier 压扁/Transformer 细长条」两症皆由此来。两处已同批修复；
    烘焙路径理论恢复可用，但保持默认关闭（nobake 已过官方对照）。"""
    # out[j*4+i] = (A·B)[i][j] = Σ_k A[i][k]·B[k][j]，列主序下 A[i][k]=A_flat[k*4+i]
    return [sum(A[k*4+i]*B[j*4+k] for k in range(4))
            for j in range(4) for i in range(4)]


def _fbx_model_world_M(f, oid):
    """Model 相对 FBX 场景根的世界矩阵 = 根侧矩阵连乘到叶。Unity 导入时
    FBX 内部节点变换会保留在节点层级上；prefab 直接引用 mesh 时这些内部
    变换必须烘进顶点（否则接线柱/电阻管等以错误姿态出现——渲染实证）。"""
    chain = []
    cur = oid
    seen = set()
    while cur and cur not in seen:
        seen.add(cur)
        chain.append(_fbx_trs_matrix(cur, f))
        parent = None
        for (ct, ch, pa, pr) in f.connections:
            if ct == 'OO' and ch == cur and pa in f.objects and f.objects[pa][0] == 'Model':
                parent = pa
                break
        cur = parent
    M = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    for m in reversed(chain):  # 根 → 叶：M = root · mid · ... · leaf
        M = _mmul(M, m)
    return M


class FBXCache:
    def __init__(self):
        self.cache = {}
    def get(self, path):
        if path in self.cache: return self.cache[path]
        f = fbx_parse(os.path.join(UNITY_ROOT, path))
        # unit: GlobalSettings UnitScaleFactor (default 1 = cm). Unity applies
        # fileScale = UnitScaleFactor to the FBX mesh, then cm->m (x0.01).
        unit = 1.0
        for ch in f.nodes:
            if ch.name == 'GlobalSettings':
                usf = p70(ch, 'UnitScaleFactor')
                if usf is not None: unit = float(usf)
        info = {'fbx': f, 'unit': unit * 0.01, 'model_geos': {}, 'geo_by_fileid': {},
                'model_world_M': {}, 'geo_M_by_fid': {}}
        name_geo = {}  # FBX 模型名 → (oid, geometry)
        for i, (oid, n) in enumerate(f.by_type('Model')):
            g = f.geometry_of(oid)
            if g:
                objname = (n.prop(1) or n.name).split('\x00', 1)[0]
                info['model_geos'].setdefault(objname, g[1])
                name_geo.setdefault(objname, (oid, g[1]))
                fid = 4300000 + 2 * i
                info['geo_by_fileid'].setdefault(fid, g[1])
                info['model_world_M'].setdefault(fid, _fbx_model_world_M(f, oid))
        # 权威映射覆盖：.meta fileIDToRecycleName 是 Unity 导入器真实分配的
        # fileID→对象名，与 FBX 遍历序不同，prefab m_Mesh.fileID 按它取几何。
        meta = fbx_meta_mesh_names(path)
        for fid, nm in sorted(meta.items()):
            if 4300000 <= fid < 4400000 and nm in name_geo:
                oid, geo = name_geo[nm]
                info['geo_by_fileid'][fid] = geo
                info['model_world_M'][fid] = _fbx_model_world_M(f, oid)
        # Geometric 烘焙：Unity 把 Model 的 Geometric* 属性烘进 Mesh 资产顶点
        # （默认全量，回退开关见文件头注释）。
        base = os.path.basename(path)
        if _GEOMETRIC_BAKE_ALL or base in GEOMETRIC_BAKE_FBXS or path in GEOMETRIC_BAKE_FBXS:
            for objname, (oid, geo) in name_geo.items():
                n = f.objects[oid][1]
                Tg = p70v3(n, 'GeometricTranslation') or [0, 0, 0]
                Rg = p70v3(n, 'GeometricRotation') or [0, 0, 0]
                Sg = p70v3(n, 'GeometricScaling') or [1, 1, 1]
                trivial = (all(abs(v) < 1e-6 for v in Tg)
                           and all(abs(v) < 1e-6 for v in Rg)
                           and all(abs(v - 1) < 1e-6 for v in Sg))
                if trivial: continue
                M = _geometric_M(Tg, Rg, Sg)
                for fid, gg in info['geo_by_fileid'].items():
                    if gg is geo:
                        info['geo_M_by_fid'][fid] = M
        self.cache[path] = info
        return info


def _geometric_M(T, Rdeg, S):
    """FBX Geometric 变换矩阵（标准语义，无轴转换）：M = T · R · S，
    列主序 flat [m00,m10,m20,tx, m01,m11,m21,ty, m02,m12,m22,tz, 0,0,0,1]。

    数值实证（2026-10-21 三轮 bbox 收敛）：
    - 底板对象016（R=0, T=(0,0,9.56)）：mesh = raw+T 后 z∈[0.03,16.21]mm，
      节点矩阵（prefab TRS 自带轴变换 1.227·(x→z,y→x,z→y)）把厚度转到
      世界 y=[0.04,19.9]mm —— 底贴 0，与官方预览一致；旧版无烘焙时
      世界 y∈[-11.7,8.2]mm 跨 0 悬空（FAIL 的「底座变薄」根因之一）。
    - pin 对象045/040（R=-90°X）：Rx(-90°)=(x,z,-y) 把柱高（raw z）转
      y，mesh 柱立于原点（x/z±7.2mm、y∈[0.14,26.61]mm）+T 归位，
      配 pin 节点 TRS（t=±0.06,0.02,0）→ 世界柱心 x=±0.06、柱底 y=20mm
      = 底板顶 19.9mm 贴合。
    教训：节点矩阵已含轴变换，Geometric 只按 FBX 标准语义直接烘——
    曾引入 swap(x,z,y) 分支（probe 枚举空间不含「无 swap」解的误判），
    渲染实证底板立起 160mm 后删除。Rdeg 为欧拉 XYZ 度（右手系）。

    欧拉合成序（2026-10-21 14:00 班修正）：R = Rz·Ry·Rx（列向量，Rx 最
    先作用）——3ds Max 导出器行向量约定下欧拉 XYZ = 列向量的 Rz·Ry·Rx。
    铁证：电容.FBX Cylinder002（GeoR=(90,-79.14,0.856)复合双轴 +
    GeoT=(3.97,-265.70,0)）：Rz·Ry·Rx 作用 raw 圆柱中心 (0,0,-265.7)
    得 (-3.97, 265.7, 0)，+GeoT 精确归零 (0,0,0)——建模 pivot 落在圆筒
    中心的必然结果；旧序 Rx·Ry·Rz 得 (265,-215,0) 偏移不抵消，圆柱飞至
    世界 y=-388~-188mm 地底（VLM 判「电容体缺失」根因）。单轴旋转两序
    等价——底板/pin/Electro05-1 等 R=-90°X 件的既有实证不受影响。"""
    rx, ry, rz = (math.radians(v) for v in Rdeg)
    cx, sx, cy, sy, cz, sz = (math.cos(rx), math.sin(rx),
                               math.cos(ry), math.sin(ry),
                               math.cos(rz), math.sin(rz))
    # R = Rz·Ry·Rx（Max 行向量欧拉 XYZ 的列向量等价形，Rx 最贴近顶点）
    R = [
        [cz*cy, -sz*cx + cz*sy*sx, sz*sx + cz*sy*cx],
        [sz*cy, cz*cx + sz*sy*sx, -cz*sx + sz*sy*cx],
        [-sy, cy*sx, cy*cx],
    ]
    # m = R·diag(S)（行主序 3x3）
    m = [[R[i][j] * S[j] for j in range(3)] for i in range(3)]
    L, t = m, [T[0], T[1], T[2]]
    # 列主序 flat
    return [L[0][0], L[1][0], L[2][0], t[0],
            L[0][1], L[1][1], L[2][1], t[1],
            L[0][2], L[1][2], L[2][2], t[2],
            0.0, 0.0, 0.0, 1.0]


def _builtin_quad_md():
    """Unity 内置 Quad 基元的网格数据（1x1 XY 平面，法线 -Z，UV 左下原点）。
    实验件用它承载符号图标（如互感器 Icon + 互感.png）与白板面。"""
    return {
        'positions': [-0.5, -0.5, 0, 0.5, -0.5, 0, -0.5, 0.5, 0, 0.5, 0.5, 0],
        'polys': [[0, 3, 1], [0, 2, 3]],
        'normals_raw': [0, 0, -1] * 4,
        'normals_mapping': 'ByVertice',
        'uvs_raw': [0, 0, 1, 0, 0, 1, 1, 1],
        'uvs_mapping': 'ByVertice',
        'uv_index': None,
        'mat_mapping': 'AllSame',
    }

BUILTIN_GUID = '0000000000000000e000000000000000'

# Unity 内置基元 fileID（BuiltinExtraIDs）：Cube/Cylinder/Sphere/Capsule/Plane/Quad。
# 实证映射：10210=Quad（270 处图标，渲染验证）；10209=Plane（Portal Laboratory
# "Shadow Plane" 命名 + Relay Icon/接地/Pin Particle 缩放语义）；10202=Cube（
# Lighthouse 浮筒 0.71×0.01×0.4 薄板）；10206/10207/10208 仅场景特效引用
# （按 Unity 惯例表 Cylinder/Sphere/Capsule 处理，不影响 87 元件）。

def _face_md(o, du, dv, n, uvs=None):
    """单面基元：o=原点，du/dv=边向量，n=法线；CCW（cross(du,dv)=n）。"""
    v0, v1, v2, v3 = o, [o[i]+du[i] for i in range(3)], [o[i]+dv[i] for i in range(3)], [o[i]+du[i]+dv[i] for i in range(3)]
    return {
        'positions': [*v0, *v1, *v2, *v3],
        'polys': [[0, 2, 1], [1, 2, 3]],
        'normals_raw': list(n) * 4,
        'normals_mapping': 'ByVertice',
        'uvs_raw': uvs or [0, 0, 1, 0, 0, 1, 1, 1],
        'uvs_mapping': 'ByVertice',
        'uv_index': None,
        'mat_mapping': 'AllSame',
    }

def _merge_mds(mds):
    """合并多面基元网格数据（重建 poly 顶点索引）。"""
    pos, polys, nrm, uvs = [], [], [], []
    for md in mds:
        base = len(pos) // 3
        pos += md['positions']
        nrm += md['normals_raw']
        uvs += md['uvs_raw']
        for p in md['polys']:
            polys.append([i + base for i in p])
    return {
        'positions': pos, 'polys': polys,
        'normals_raw': nrm, 'normals_mapping': 'ByVertice',
        'uvs_raw': uvs, 'uvs_mapping': 'ByVertice',
        'uv_index': None, 'mat_mapping': 'AllSame',
    }

def _builtin_primitive_md(fid):
    """Unity 内置基元的网格数据（Unity 本地空间，Y 上，米制：随 prefab 缩放）。"""
    if fid == 10210:
        return _builtin_quad_md()
    if fid == 10209:
        # Plane：10x10 XZ 平面，法线 +Y
        return _face_md([-5, 0, -5], [10, 0, 0], [0, 0, 10], [0, 1, 0])
    if fid == 10202:
        # Cube：1x1x1 居中，6 面独立法线
        faces = [
            (_face_md([-0.5, -0.5, -0.5], [1, 0, 0], [0, 0, 1], [0, 0, -1])),   # -Z
            (_face_md([0.5, -0.5, 0.5], [-1, 0, 0], [0, 0, -1], [0, 0, 1])),    # +Z
            (_face_md([-0.5, -0.5, 0.5], [0, 0, -1], [0, 1, 0], [-1, 0, 0])),   # -X
            (_face_md([0.5, -0.5, -0.5], [0, 0, 1], [0, 1, 0], [1, 0, 0])),     # +X
            (_face_md([-0.5, 0.5, -0.5], [1, 0, 0], [0, 0, 1], [0, 1, 0])),     # +Y
            (_face_md([-0.5, -0.5, 0.5], [1, 0, 0], [0, 0, -1], [0, -1, 0])),   # -Y
        ]
        return _merge_mds(faces)
    if fid == 10206:
        # Cylinder：r=0.5, h=2（Y -1..1），48 段侧面 + 双端盖
        import math
        N = 48
        side, caps = [], []
        for i in range(N):
            a0, a1 = 2*math.pi*i/N, 2*math.pi*(i+1)/N
            c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
            n0 = [c0, 0, s0]; n1 = [c1, 0, s1]
            side.append({
                'positions': [0.5*c0, -1, 0.5*s0, 0.5*c1, -1, 0.5*s1, 0.5*c0, 1, 0.5*s0, 0.5*c1, 1, 0.5*s1],
                'polys': [[0, 2, 1], [1, 2, 3]],
                'normals_raw': [*n0, *n1, *n0, *n1],
                'normals_mapping': 'ByVertice',
                'uvs_raw': [i/N, 0, (i+1)/N, 0, i/N, 1, (i+1)/N, 1],
                'uvs_mapping': 'ByVertice', 'uv_index': None, 'mat_mapping': 'AllSame',
            })
            caps.append({
                'positions': [0, -1, 0, 0.5*c0, -1, 0.5*s0, 0.5*c1, -1, 0.5*s1],
                'polys': [[0, 1, 2]], 'normals_raw': [0, -1, 0]*3,
                'normals_mapping': 'ByVertice', 'uvs_raw': [0.5, 0.5, 0.5+0.5*c0, 0.5+0.5*s0, 0.5+0.5*c1, 0.5+0.5*s1],
                'uvs_mapping': 'ByVertice', 'uv_index': None, 'mat_mapping': 'AllSame',
            })
            caps.append({
                'positions': [0, 1, 0, 0.5*c0, 1, 0.5*s0, 0.5*c1, 1, 0.5*s1],
                'polys': [[0, 2, 1]], 'normals_raw': [0, 1, 0]*3,
                'normals_mapping': 'ByVertice', 'uvs_raw': [0.5, 0.5, 0.5+0.5*c0, 0.5+0.5*s0, 0.5+0.5*c1, 0.5+0.5*s1],
                'uvs_mapping': 'ByVertice', 'uv_index': None, 'mat_mapping': 'AllSame',
            })
        return _merge_mds(side + caps)
    if fid in (10207, 10208):
        # Sphere：r=0.5；Capsule：r=0.5 圆柱段 h=1 + 上下半球（总高 2）
        import math
        sphere = fid == 10207
        pos, polys, nrm, uvs = [], [], [], []
        W, H = 32, 24 if sphere else 12
        rings = []
        for j in range(H + 1):
            ring = []
            if sphere:
                phi = -math.pi/2 + math.pi*j/H
                y, r = 0.5*math.sin(phi), 0.5*math.cos(phi)
                ny, nr = math.sin(phi), math.cos(phi)
            else:
                if j <= H/2:
                    phi = -math.pi/2 + (math.pi/2)*(j/(H/2))
                    y = -0.5 + 0.5*math.sin(phi)
                    ny, nr = math.sin(phi), math.cos(phi)
                else:
                    phi = (math.pi/2)*((j-H/2)/(H/2))
                    y = 0.5 + 0.5*math.sin(phi)
                    ny, nr = math.sin(phi), math.cos(phi)
            for i in range(W):
                th = 2*math.pi*i/W
                ring.append(len(pos)//3)
                pos += [r*math.cos(th), y, r*math.sin(th)]
                nrm += [nr*math.cos(th), ny, nr*math.sin(th)]
                uvs += [i/W, j/H]
            rings.append(ring)
        for j in range(H):
            for i in range(W):
                i2 = (i+1) % W
                polys += [[rings[j][i], rings[j+1][i], rings[j][i2]],
                          [rings[j][i2], rings[j+1][i], rings[j+1][i2]]]
        return {'positions': pos, 'polys': polys, 'normals_raw': nrm,
                'normals_mapping': 'ByVertice', 'uvs_raw': uvs,
                'uvs_mapping': 'ByVertice', 'uv_index': None, 'mat_mapping': 'AllSame'}
    raise ValueError(f'unsupported builtin primitive fileID={fid}')

BUILTIN_PRIMS = {10202, 10206, 10207, 10208, 10209, 10210}


def extract_component(prefab_path, ua, fbx_cache, out_dir):
    pf = parse_prefab(prefab_path)
    tree = scene_tree(pf)
    if not tree: return None
    root = tree[0]
    # CircuitComponent MonoBehaviour = the 114 comp on root
    cc = None
    for c in root['components']:
        if c['class'] == 114:
            cc = c['data']; break
    if not cc or not cc.get('ModelID'): return None
    model_id = cc['ModelID']
    friendly = cc.get('FriendlyName', model_id)
    categories = cc.get('Categories') or []
    glb = GLB()
    fbx_cache_ = fbx_cache
    stats = {'meshes': 0, 'verts': 0}

    def emit_node(node, parent_children, skip_pin_meshes=False, top_level=False):
        comps = {c['class']: c['data'] for c in node['components']}
        mesh_idx = None
        mf = comps.get(33)  # MeshFilter
        mr = comps.get(23)  # MeshRenderer
        is_pin_node = str(node['name'] or '').lower().startswith('pin')
        if mf and mr and node.get('active', 1) and not (skip_pin_meshes and is_pin_node):
            mesh_ref = mf.get('m_Mesh')
            if isinstance(mesh_ref, dict) and mesh_ref.get('guid'):
                fbx_path = ua.guid_map.get(mesh_ref['guid'])
                if fbx_path and fbx_path.lower().endswith('.fbx'):
                    info = fbx_cache_.get(fbx_path)
                    fid = mesh_ref.get('fileID', 0)
                    geo = info['geo_by_fileid'].get(fid)
                    if geo is None:
                        geo = info['model_geos'].get(node['name'])
                    if geo is not None:
                        md = mesh_data(geo)
                        if md:
                            fbx_M = info.get('model_world_M', {}).get(fid)
                            if (model_id, node['name'] or '') in NODE_SKIP_FBX_M:
                                fbx_M = None  # 双重变换豁免（NODE_SKIP_FBX_M，见定义处注释）
                            geo_M = info.get('geo_M_by_fid', {}).get(fid)
                            mesh_idx = _emit_mesh(glb, node, md, info, mr, ua, fbx_M, geo_M,
                                                   flip_winding=(model_id, node['name'] or '') in NODE_MESH_WINDING_FLIP)
                            stats['meshes'] += 1
                            stats['verts'] += len(md['positions']) // 3
                elif mesh_ref.get('guid') == BUILTIN_GUID and mesh_ref.get('fileID') in BUILTIN_PRIMS:
                    # Unity 内置基元（Quad 承载符号图标/白板，Plane 为接地/Icon 面片），
                    # 顶点为 Unity 本地空间数据，走与 FBX 同一条 conv 发射管线
                    md = _builtin_primitive_md(mesh_ref['fileID'])
                    mesh_idx = _emit_mesh(glb, node, md, {'unit': 1.0}, mr, ua)
                    stats['meshes'] += 1
                    stats['verts'] += len(md['positions']) // 3
        mat = trs_matrix(node['transform'], top_level=top_level)
        # 2026-10-23 P0：NODE_LOCAL_YFLIP —— 后乘 diag(1,-1,1)（本地 y 轴翻转，
        # 列主序 flat 下 = col1 三元素取负）。机理与验证见文件头注释块。
        if (model_id, node['name'] or '') in NODE_LOCAL_YFLIP and not top_level:
            mat[4] = -mat[4]; mat[5] = -mat[5]; mat[6] = -mat[6]
        node_idx = glb.add_node(node['name'] or 'node', mesh=mesh_idx,
                                 matrix=mat)
        parent_children.append(node_idx)
        child_root = glb.json['nodes'][node_idx].setdefault('children', [])
        for ch in node['children']:
            emit_node(ch, child_root, skip_pin_meshes)
        return node_idx

    root_children = glb.json['scenes'][0]['nodes']
    # root transform itself is identity for components; start at children of root
    for ch in root['children']:
        emit_node(ch, root_children, skip_pin_meshes=not KEEP_PIN_MESHES, top_level=True)
    # 顶层一次 S：X_MIRROR 包装节点（diag(-1,1,1)）承载整个组件的 x 镜像，
    # 取代旧管线的「每层 R 共轭 + 顶点 S」。write() 以未被引用节点为场景根，
    # 包装后场景根自动只剩 X_MIRROR。
    # 注意：scenes[0]['nodes'] 初始含默认 [0]（与首个真实节点同索引），去重防双挂。
    real = [i for i in dict.fromkeys(root_children) if i < len(glb.json['nodes'])]
    if MIRROR_X and real:
        wrap = glb.add_node('X_MIRROR', matrix=[-1, 0, 0, 0, 0, 1, 0, 0,
                                                0, 0, 1, 0, 0, 0, 0, 1])
        glb.json['nodes'][wrap]['children'] = real

    # pins
    pins = []
    for pref in (cc.get('Pins') or []):
        pid = pref.get('fileID') if isinstance(pref, dict) else None
        if not pid: continue
        mb = pf['monobehaviours'].get(pid)
        if not mb: continue
        go_id = mb.get('m_GameObject', {}).get('fileID')
        go = pf['gameobjects'].get(go_id, {})
        # find pin transform: search transforms whose m_GameObject == go_id
        pin_tr = None
        for fid, tr in pf['transforms'].items():
            if tr.get('m_GameObject', {}).get('fileID') == go_id:
                pin_tr = tr; break
        if pin_tr is None: continue
        # world position: compose up to root (root is at origin)
        pos = _world_pos(pf, pin_tr)
        pins.append({
            'name': safe_name(go.get('m_Name', '')),
            'position': conv_pos(pos, 1.0),
            'isPositive': bool(mb.get('IsPositive', 0)),
        })
    # root local rotation/position from CircuitComponent root transform (usually identity)
    label_offset = cc.get('LabelHeight', 0.08)
    out = {
        'ModelID': model_id,
        'FriendlyName': friendly,
        'Categories': categories if isinstance(categories, list) else [str(categories)],
        'pins': pins,
        'limitSize': cc.get('LimitSize'),
        'schematic': False,
    }
    os.makedirs(out_dir, exist_ok=True)
    safe = model_id.replace('/', '_').replace(' ', '_')
    total = glb.write(os.path.join(out_dir, safe + '.glb'))
    out['glb'] = safe + '.glb'
    out['glbBytes'] = total
    return out


def _world_pos(pf, tr):
    """Prefab 内变换链的世界位置：祖先 S,R,T 全链组合（旧版漏乘祖先 scale，
    还把自身 scale 误乘进自身坐标——电流表 pin 因此算到 -5.15m）。
    注意：结果为 Unity 空间（米），调用方负责镜像到 GLB 空间。"""
    p = tr.get('m_LocalPosition', {})
    v = [p.get('x', 0), p.get('y', 0), p.get('z', 0)]
    father = tr.get('m_Father', {}).get('fileID')
    while father:
        ptr = pf['transforms'].get(father)
        if not ptr: break
        s = ptr.get('m_LocalScale', {})
        v = [v[i] * s.get('xyz'[i], 1) for i in range(3)]
        pq = ptr.get('m_LocalRotation', {})
        pqq = [pq.get('x', 0), pq.get('y', 0), pq.get('z', 0), pq.get('w', 1)]
        v = _qrot_apply(pqq, v)
        pp = ptr.get('m_LocalPosition', {})
        v = [v[0]+pp.get('x', 0), v[1]+pp.get('y', 0), v[2]+pp.get('z', 0)]
        father = ptr.get('m_Father', {}).get('fileID')
    return v

def _qrot_apply(q, v):
    x, y, z = v; qx, qy, qz, qw = q
    t = [qw*x + qy*z - qz*y, qw*y + qz*x - qx*z, qw*z + qx*y - qy*x]
    return [x + 2*(qy*t[2]-qz*t[1]), y + 2*(qz*t[0]-qx*t[2]), z + 2*(qx*t[1]-qy*t[0])]

def _emit_mesh(glb, node, md, info, mr, ua, fbx_M=None, geo_M=None, flip_winding=False):
    """Emit an FBX mesh as glTF primitives with per-corner vertex expansion.
    fbx_M: FBX 内部节点链世界矩阵（列主序 4x4，原始单位），烘进顶点/法线，
    使 prefab 直接引用 mesh 时与 Unity 导入效果一致（BAKE_FBX_M=1 时生效）。
    geo_M: Geometric 烘焙矩阵（白名单 FBX，管线空间列主序 4x4，原始单位），
    Unity 导入语义下 Geometric* 总是烘进顶点——不受 BAKE_FBX_M 开关控制。
    应用次序：顶点 = fbx_M · (geo_M · v)，先几何级后节点级。"""
    unit = info['unit']
    verts = md['positions']
    IDENT = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    if geo_M and geo_M != IDENT:
        nv = len(verts) // 3
        gb = [0.0] * (nv * 3)
        # 列主序 flat：平移分量在 [3]/[7]/[11]（第四行是 [12..15]=0,0,0,1）
        # 旧代码误读 [12]/[13]/[14] —— 平移从未生效（bbox 实证：柱心偏 Tx/Tz）
        for i in range(nv):
            x, y, z = verts[i*3], verts[i*3+1], verts[i*3+2]
            gb[i*3]   = geo_M[0]*x + geo_M[4]*y + geo_M[8]*z + geo_M[3]
            gb[i*3+1] = geo_M[1]*x + geo_M[5]*y + geo_M[9]*z + geo_M[7]
            gb[i*3+2] = geo_M[2]*x + geo_M[6]*y + geo_M[10]*z + geo_M[11]
        verts = gb
        # 法线 raw 同步烘 Geometric 线性部分（md 每次重新解析，就地改安全）
        nr_geo = md.get('normals_raw')
        if nr_geo:
            for i in range(len(nr_geo) // 3):
                nx, ny, nz = nr_geo[i*3], nr_geo[i*3+1], nr_geo[i*3+2]
                nr_geo[i*3]   = geo_M[0]*nx + geo_M[4]*ny + geo_M[8]*nz
                nr_geo[i*3+1] = geo_M[1]*nx + geo_M[5]*ny + geo_M[9]*nz
                nr_geo[i*3+2] = geo_M[2]*nx + geo_M[6]*ny + geo_M[10]*nz
    if not BAKE_FBX_M:
        fbx_M = None   # 不烘：顶点保持 Model 局部空间（Unity 导入语义）
    if fbx_M and fbx_M != [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]:
        nv = len(verts) // 3
        baked = [0.0] * (nv * 3)
        # 同款下标修复：列主序平移在 [3]/[7]/[11]（旧 [12..14] 读的是 0,0,0 行）
        for i in range(nv):
            x, y, z = verts[i*3], verts[i*3+1], verts[i*3+2]
            baked[i*3]   = fbx_M[0]*x + fbx_M[4]*y + fbx_M[8]*z + fbx_M[3]
            baked[i*3+1] = fbx_M[1]*x + fbx_M[5]*y + fbx_M[9]*z + fbx_M[7]
            baked[i*3+2] = fbx_M[2]*x + fbx_M[6]*y + fbx_M[10]*z + fbx_M[11]
        verts = baked
        # 法线的线性部分变换在逐角循环里做
    def _bake_normal(nx, ny, nz):
        if not fbx_M or fbx_M == [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]:
            return [nx, ny, nz]
        return [fbx_M[0]*nx + fbx_M[4]*ny + fbx_M[8]*nz,
                fbx_M[1]*nx + fbx_M[5]*ny + fbx_M[9]*nz,
                fbx_M[2]*nx + fbx_M[6]*ny + fbx_M[10]*nz]
    polys = md['polys']
    nm = md.get('normals_mapping', 'ByPolygonVertex')
    nr = md.get('normals_raw') or []
    um = md.get('uvs_mapping', 'ByPolygonVertex')
    ur = md.get('uvs_raw') or []
    uvi = md.get('uv_index')
    # ---- 材质槽（Unity submesh 对齐）----
    mat_mapping = md.get('mat_mapping', 'AllSame')
    mat_indices = md.get('mat_indices') or []

    def _slot_of_poly(pi, corner):
        if mat_mapping == 'ByPolygon' and pi < len(mat_indices):
            return int(mat_indices[pi])
        if mat_mapping == 'ByPolygonVertex' and corner < len(mat_indices):
            return int(mat_indices[corner])
        return 0

    # ---- 解析 renderer 全部材质槽 ----
    parsed_mats = []
    mats = mr.get('m_Materials') or []
    for mref in mats:
        m = None
        if isinstance(mref, dict) and mref.get('guid'):
            mat_path = ua.guid_map.get(mref['guid'])
            if mat_path and mat_path.endswith('.mat'):
                m = parse_material(os.path.join(UNITY_ROOT, mat_path))
                m['name'] = os.path.splitext(os.path.basename(mat_path))[0]
                if m.get('maintex'):
                    m['maintex_path'] = ua.guid_map.get(m['maintex'])
        parsed_mats.append(m)
    if not parsed_mats:
        parsed_mats = [None]

    def _matidx_for_slot(slot):
        if slot < len(parsed_mats):
            m = parsed_mats[slot]
        else:
            m = None
        if m is None:
            return glb.add_material({'name': f'default_s{slot}'})
        return glb.add_material(m)

    # 顶点槽位预解析（避免逐角重复查询）：每 poly 记录每角的法线/UV 索引
    per_poly_meta = []  # (slot, [(cx, bi, ui), ...])
    corner = 0
    for pi, poly in enumerate(polys):
        if len(poly) < 3:
            corner += len(poly)
            continue
        slot = _slot_of_poly(pi, corner)
        metas = []
        for k, cx in enumerate(poly):
            bi = None
            if nr:
                if nm == 'ByPolygonVertex': bi = (corner + k) * 3
                elif nm == 'ByVertice': bi = cx * 3
                else: bi = 0
                if bi is not None and bi >= len(nr): bi = None
            ui = None
            if ur:
                if uvi is not None and (corner + k) < len(uvi):
                    ui = uvi[corner + k] * 2
                elif um == 'ByVertice':
                    ui = cx * 2
                else:
                    ui = (corner + k) * 2
                if ui is not None and ui + 1 >= len(ur): ui = None
            metas.append((cx, bi, ui))
        per_poly_meta.append((slot, metas))
        corner += len(poly)

    # Unity 导入语义：Mesh 的子网格号 = 该几何实际用到的 FBX 材质索引按
    # 升序重编（renderer.m_Materials 与子网格一一对应）。FBX 原始索引可能
    # 跳号（如几何只用 1 号材质），直接透传会错位成 default_s{slot}。
    used = sorted({s for s, _ in per_poly_meta})
    rank = {m: i for i, m in enumerate(used)}
    per_poly_meta = [(rank[s], mt) for s, mt in per_poly_meta]

    # 按材质槽聚合 primitive
    groups = {}
    for slot, metas in per_poly_meta:
        g = groups.setdefault(slot, {'positions': [], 'normals': [], 'uvs': [], 'indices': [], 'vc': 0})
        np_ = len(metas)
        base = g['vc']
        for (cx, bi, ui) in metas:
            g['positions'].extend(conv_pos(verts[cx*3:cx*3+3], unit, mirror_x=False))
            # NODE_MESH_WINDING_FLIP：弃原始法线，兜底 _face_normals 从翻后
            # indices 重算（与剔除方向自洽）；原始 ByPolygonVertex 值与新 winding 矛盾。
            if nr and bi is not None and not flip_winding:
                bn = _bake_normal(nr[bi], nr[bi+1], nr[bi+2])
                g['normals'].extend(conv_normal(bn, mirror_x=False))
            if ur and ui is not None:
                g['uvs'].extend([ur[ui], 1.0 - ur[ui+1]])
            g['vc'] += 1
        for k in range(1, np_ - 1):
            if flip_winding:
                g['indices'].extend([base, base + k + 1, base + k])
            else:
                g['indices'].extend([base, base + k, base + k + 1])

    # 无多边形的兜底（理论上不会走到）
    if not groups:
        return None

    if len(groups) == 1:
        slot, g = next(iter(groups.items()))
        # 2026-10-22b 修复内翻：X_MIRROR(det=-1) 下 three.js frontFaceCW 已反转
        # 剔除方向，顶点不镜像时索引必须保持原 winding（多翻一次=实心变空托盘）
        if not g['normals']:
            g['normals'] = _face_normals(g['positions'], g['indices'])
        matidx = _matidx_for_slot(slot)
        return glb.add_mesh(node['name'], g['positions'], g['normals'], g['uvs'], g['indices'], matidx)

    # 多材质：每槽一个 primitive，材质槽号对应 m_Materials[slot]
    prims = []
    for slot in sorted(groups):
        g = groups[slot]
        # 2026-10-22b 修复内翻：X_MIRROR(det=-1) 下 three.js frontFaceCW 已反转
        # 剔除方向，顶点不镜像时索引必须保持原 winding（多翻一次=实心变空托盘）
        if not g['normals']:
            g['normals'] = _face_normals(g['positions'], g['indices'])
        prims.append({'positions': g['positions'], 'normals': g['normals'],
                      'uvs': g['uvs'] or None, 'indices': g['indices'],
                      'matidx': _matidx_for_slot(slot)})
    return glb.add_mesh_multi(node['name'], prims)

def _face_normals(positions, indices):
    normals = [0.0] * (len(positions) // 3 * 3)
    for i in range(0, len(indices), 3):
        a, b, c = indices[i]*3, indices[i+1]*3, indices[i+2]*3
        ux, uy, uz = positions[b]-positions[a], positions[b+1]-positions[a+1], positions[b+2]-positions[a+2]
        vx, vy, vz = positions[c]-positions[a], positions[c+1]-positions[a+1], positions[c+2]-positions[a+2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        for idx in (a, b, c):
            normals[idx] += nx; normals[idx+1] += ny; normals[idx+2] += nz
    out = []
    for i in range(0, len(normals), 3):
        l = math.sqrt(normals[i]**2 + normals[i+1]**2 + normals[i+2]**2) or 1.0
        out.extend([normals[i]/l, normals[i+1]/l, normals[i+2]/l])
    return out


def main():
    ua = UnityAssets()
    fbx_cache = FBXCache()
    exp_dir = os.path.join(OUT_ROOT, 'components')
    os.makedirs(exp_dir, exist_ok=True)
    import glob
    prefabs = glob.glob(os.path.join(UNITY_ROOT, 'Assets/Resources/Experiments/**/*.prefab'), recursive=True)
    catalog = []
    for p in sorted(prefabs):
        try:
            entry = extract_component(p, ua, fbx_cache, exp_dir)
            if entry:
                catalog.append(entry)
                print(f"OK  {entry['ModelID']:<28} pins={len(entry['pins'])} meshes={entry['glbBytes']}B")
            else:
                print(f'SKIP {os.path.basename(p)}')
        except Exception as e:
            print(f'ERR {os.path.basename(p)}: {e}')
    with open(os.path.join(OUT_ROOT, 'catalog.json'), 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=1)
    # 配置烙印（2026-10-23 P2 根因结案后上线）：任何产物可追溯生成配置。
    # 动机——「跨会话旋转列符号相反」悬案实证（tools/probe_determinism.py，
    # 8 组合×8 一致）：提取链纯确定，历史差异实为中间态代码/实验环境变量
    # 漂移。烙印后配置漂移一眼可辨，不再依赖推理。
    import subprocess as _sp
    try:
        head = _sp.check_output(['git', 'rev-parse', 'HEAD'],
                                cwd=os.path.dirname(OUT_ROOT), text=True).strip()[:12]
    except Exception:
        head = 'unknown'
    meta = {
        'gitHead': head,
        'generatedAt': __import__('time').strftime('%Y-%m-%dT%H:%M:%S'),
        'extractConfig': {
            'MIRROR_FIX': os.environ.get('MIRROR_FIX', 's3gen'),
            'BAKE_FBX_M': os.environ.get('BAKE_FBX_M', '0'),
            'KEEP_PIN_MESHES': os.environ.get('KEEP_PIN_MESHES', '1'),
            'GEOMETRIC_BAKE_FBXS': os.environ.get('GEOMETRIC_BAKE_FBXS', '*'),
            'NODE_LOCAL_YFLIP': sorted(NODE_LOCAL_YFLIP) if 'NODE_LOCAL_YFLIP' in globals() else None,
            'NODE_MESH_WINDING_FLIP': sorted(NODE_MESH_WINDING_FLIP),
        },
    }
    with open(os.path.join(OUT_ROOT, 'catalog.meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    # 拨杆不变量自动检查（非确定性防御，tools/check_switch_pole.py 固化）
    sw = os.path.join(exp_dir, 'Simple Switch.glb')
    if os.path.exists(sw):
        r = _sp.run([sys.executable, os.path.join(os.path.dirname(__file__),
                                                  'check_switch_pole.py'), sw])
        if r.returncode != 0:
            print('CHECK-FAIL: check_switch_pole.py 不变量被违反，提取产物可疑，中止')
            sys.exit(1)
    print(f'\nTotal {len(catalog)} components -> {exp_dir}')

if __name__ == '__main__':
    main()

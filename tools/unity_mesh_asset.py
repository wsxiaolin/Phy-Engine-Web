#!/usr/bin/env python3
"""Unity YAML Mesh .asset decoder (m_VertexData channel-streams format).

Unity Mesh serializedVersion>=9 打包顶点到 m_VertexData._typelessdata 的
channel streams（旧版 m_Vertices packed 数组已废弃）。emit_node 的 FBX-only
分支此前静默跳过这类资产 → Photoresistor 主体「光敏电阻 1.asset」丢失
（第 16/17 轮画像，2026-10-24 修复）。

输出 md dict 与 extract_components._emit_mesh / FBX mesh_data 契约对齐：
  positions        flat [x,y,z,...]（Unity 本地空间，米制）
  normals_raw      flat（ByVertice 映射）
  uvs_raw          flat（ByVertice，通道 uv0 存在时）
  polys            [[a,b,c], ...]（Unity 原始三角形序；X 镜像绕序翻转
                   由发射管线统一处理，与 FBX 路径同权）
  mat_mapping      单 submesh='AllSame'；多 submesh='ByPolygon' +
                   mat_indices（每三角形材质槽，与 MeshRenderer 槽序对齐）

解析策略：行级缩进游标（YAML 字段名全局唯一性不足，正则全文匹配有
m_Shapes 误配风险）；hex blob 用 [0-9a-fA-F\\s]* 类匹配自动停在首个
非 hex 字符（'m' 不在 a-f 内，行首 'm_...' 天然终止）。
"""
import re
import struct

# kChannelFormat -> (字节数, 是否需要归一化映射到 [0,1]/[-1,1])
_FMT = {
    0: (4, None),   # kFloat32
    1: (2, 'half'),  # kFloat16
    2: (1, (0.0, 1.0)),    # kUNorm8
    3: (1, (-1.0, 1.0)),   # kSNorm8
    4: (2, (0.0, 1.0)),    # kUNorm16
    5: (2, (-1.0, 1.0)),   # kSNorm16
    6: (1, None), 7: (1, None),   # UInt8 / Int8（整型，按分量原值）
    8: (2, None), 9: (2, None),   # UInt16 / Int16
    10: (4, None), 11: (4, None),  # UInt32 / Int32
}

# m_Channels 数组下标 -> 语义（Unity VertexAttribute 顺序）
# 0 position, 1 normal, 2 tangent, 3 color, 4..8 uv0..uv4
_ATTR_POS, _ATTR_NRM, _ATTR_UV0 = 0, 1, 4


def _sec_lines(lines, start_key, end_pred):
    """收集 start_key 行之后、直到 end_pred(同级键) 的区段行（含缩进任意子行）。"""
    out, in_sec, key_indent = [], False, None
    for ln in lines:
        m = re.match(r'(\s*)([A-Za-z_][A-Za-z0-9_]*):', ln)
        if in_sec and m:
            ind = len(m.group(1))
            if ind <= key_indent and end_pred(m.group(2)):
                break
        if not in_sec and m and m.group(2) == start_key:
            in_sec = True
            key_indent = len(m.group(1))
            continue
        if in_sec:
            out.append(ln)
    return out


def _parse_channels(lines):
    chs, cur = [], None
    for ln in lines:
        m = re.match(r'\s+- stream:\s*(\d+)\s*$', ln)
        if m:
            if cur:
                chs.append(cur)
            cur = {'stream': int(m.group(1))}
            continue
        if cur is None:
            continue
        for k in ('offset', 'format', 'dimension'):
            m = re.match(r'\s+%s:\s*(-?\d+)\s*$' % k, ln)
            if m:
                cur[k] = int(m.group(1))
                break
        if len(cur) == 4:
            chs.append(cur)
            cur = None
    return chs


def _parse_submeshes(lines):
    sms, cur = [], None
    for ln in lines:
        m = re.match(r'\s+- serializedVersion:', ln)
        if m:
            if cur:
                sms.append(cur)
            cur = {}
            continue
        if cur is None:
            continue
        for k in ('firstByte', 'indexCount', 'topology', 'baseVertex', 'firstVertex', 'vertexCount'):
            m = re.match(r'\s+%s:\s*(\d+)\s*$' % k, ln)
            if m:
                cur[k] = int(m.group(1))
                break
    if cur:
        sms.append(cur)
    return [s for s in sms if 'indexCount' in s]


def _hex_blob(text, key):
    m = re.search(r'%s:\s*([0-9a-fA-F\s]*)' % key, text)
    return m.group(1) if m else None


def _read_channel(data, chs, attr, vcount):
    ch = chs[attr] if attr < len(chs) else None
    if not ch or ch.get('dimension', 0) <= 0:
        return None
    nbytes, norm = _FMT[ch.get('format', 0)]
    dim = ch['dimension']
    stride = sum(_FMT[c.get('format', 0)][0] * c.get('dimension', 0)
                 for c in chs if c.get('dimension', 0) > 0 and c['stream'] == ch['stream'])
    # stream 基偏移：多 stream 按 stream 号升序紧密堆叠（本工程仅见 stream 0）
    base = 0
    for s in sorted({c['stream'] for c in chs if c.get('dimension', 0) > 0}):
        if s == ch['stream']:
            break
        st = sum(_FMT[c.get('format', 0)][0] * c.get('dimension', 0)
                 for c in chs if c.get('dimension', 0) > 0 and c['stream'] == s)
        base += st * vcount
    out = []
    for i in range(vcount):
        off = base + i * stride + ch['offset']
        vals = []
        for d in range(dim):
            b = data[off + d * nbytes: off + (d + 1) * nbytes]
            if len(b) < nbytes:
                return None
            if ch['format'] == 0:
                v = struct.unpack('<f', b)[0]
            elif ch['format'] == 1:
                v = struct.unpack('<e', b)[0]
            elif ch['format'] in (2, 3):
                v = struct.unpack('<B', b)[0]
                if norm:
                    v = norm[0] + v * (norm[1] - norm[0]) / 255.0
            elif ch['format'] in (4, 5):
                v = struct.unpack('<H', b)[0]
                if norm:
                    v = norm[0] + v * (norm[1] - norm[0]) / 65535.0
            elif ch['format'] == 7:
                v = struct.unpack('<b', b)[0]
            elif ch['format'] == 9:
                v = struct.unpack('<h', b)[0]
            elif ch['format'] == 11:
                v = struct.unpack('<i', b)[0]
            else:
                v = struct.unpack('<I' if nbytes == 4 else '<H', b)[0]
            vals.append(v)
        out.extend(vals[:dim])
    return out


def parse_mesh_asset(path):
    """Unity YAML Mesh .asset -> md dict（契约见模块 docstring）。失败返回 None。"""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    lines = text.split('\n')
    try:
        vcount = int(re.search(r'm_VertexCount:\s*(\d+)', text).group(1))
    except AttributeError:
        return None
    # channels / submeshes 走区段游标（防 m_Shapes 同名字段误配）
    chs = _parse_channels(_sec_lines(lines, 'm_Channels', lambda k: True))
    if not chs:
        return None
    sms = _parse_submeshes(_sec_lines(lines, 'm_SubMeshes', lambda k: True))
    idx_fmt_m = re.search(r'm_IndexFormat:\s*(\d+)', text)
    idx_fmt = int(idx_fmt_m.group(1)) if idx_fmt_m else 0
    vhex, ihex = _hex_blob(text, '_typelessdata'), _hex_blob(text, 'm_IndexBuffer')
    if not vhex or not ihex or vcount <= 0:
        return None
    data = bytes.fromhex(''.join(vhex.split()))
    ibuf = bytes.fromhex(''.join(ihex.split()))
    pos = _read_channel(data, chs, _ATTR_POS, vcount)
    if not pos:
        return None
    md = {
        'positions': pos,
        'normals_raw': _read_channel(data, chs, _ATTR_NRM, vcount) or [],
        'normals_mapping': 'ByVertice',
        'uvs_raw': _read_channel(data, chs, _ATTR_UV0, vcount) or [],
        'uvs_mapping': 'ByVertice',
        'uv_index': None,
        'mat_mapping': 'AllSame',
    }
    # 索引（uint16/uint32 连续流，submesh 按 firstByte 切片）
    idx = list(struct.unpack('<%dH' % (len(ibuf) // 2), ibuf)) if idx_fmt == 0 \
        else list(struct.unpack('<%dI' % (len(ibuf) // 4), ibuf))
    polys, mat_idx = [], []
    use_sub = [s for s in sms if s.get('topology', 0) == 0 and s.get('indexCount', 0) >= 3]
    if not use_sub:
        use_sub = [{'firstByte': 0, 'indexCount': len(idx)}]
    if len(use_sub) > 1:
        md['mat_mapping'] = 'ByPolygon'
    for slot, s in enumerate(use_sub):
        step = 2 if idx_fmt == 0 else 4
        a = s['firstByte'] // step
        n = s['indexCount']
        for t in range(n // 3):
            tri = idx[a + t * 3: a + t * 3 + 3]
            polys.append(tri)
            if len(use_sub) > 1:
                mat_idx.append(slot)
    if not polys:
        return None
    md['polys'] = polys
    if mat_idx:
        md['mat_indices'] = mat_idx
    return md


if __name__ == '__main__':
    import sys
    import json
    md = parse_mesh_asset(sys.argv[1])
    if not md:
        print('PARSE FAILED')
        sys.exit(1)
    p = md['positions']
    xs, ys, zs = p[0::3], p[1::3], p[2::3]
    print('verts:', len(p) // 3, 'polys:', len(md['polys']),
          'normals:', len(md['normals_raw']) // 3, 'uvs:', len(md['uvs_raw']) // 2,
          'mat_mapping:', md['mat_mapping'])
    print('bbox: x[%.3f %.3f] y[%.3f %.3f] z[%.3f %.3f]' %
          (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
    # 抽查三角形面积非零（防索引错位产生退化面）
    bad = 0
    for tri in md['polys'][:2000]:
        a, b, c = (md['positions'][tri[0] * 3:tri[0] * 3 + 3],
                   md['positions'][tri[1] * 3:tri[1] * 3 + 3],
                   md['positions'][tri[2] * 3:tri[2] * 3 + 3])
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        cr = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        if abs(cr[0]) + abs(cr[1]) + abs(cr[2]) < 1e-9:
            bad += 1
    print('degenerate tris in first 2000:', bad)

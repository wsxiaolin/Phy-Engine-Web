#!/usr/bin/env python3
"""Binary FBX 7.x parser (subset sufficient for mesh/material extraction)."""
import struct, zlib, sys, io

FBX_MAGIC = b'Kaydara FBX Binary  \x00'

class Node:
    __slots__ = ('name', 'props', 'children')
    def __init__(self, name):
        self.name = name
        self.props = []      # list of (typecode, value)
        self.children = []
    def find(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None
    def find_all(self, name):
        return [c for c in self.children if c.name == name]
    def prop(self, i):
        return self.props[i][1] if i < len(self.props) else None
    def __repr__(self):
        return f'<Node {self.name} props={len(self.props)} children={len(self.children)}>'

def _read_prop(f, tc):
    if tc == b'I': return (tc, struct.unpack('<i', f.read(4))[0])
    if tc == b'L': return (tc, struct.unpack('<q', f.read(8))[0])
    if tc == b'D': return (tc, struct.unpack('<d', f.read(8))[0])
    if tc == b'F': return (tc, struct.unpack('<f', f.read(4))[0])
    if tc == b'C': return (tc, bool(f.read(1)))
    if tc in (b'S', b'R'):
        ln = struct.unpack('<I', f.read(4))[0]
        data = f.read(ln)
        if tc == b'S':
            data = data.decode('utf-8', 'replace')
        return (tc, data)
    if tc in (b'f', b'd', b'l', b'i', b'b'):
        alen, enc, clen = struct.unpack('<III', f.read(12))
        data = f.read(clen)
        if enc == 1:
            data = zlib.decompress(data)
        fmt = {b'f':'f', b'd':'d', b'l':'q', b'i':'i', b'b':'?'}[tc]
        size = struct.calcsize('<' + fmt)
        n = alen
        if len(data) < n * size:  # truncated / padded
            n = len(data) // size
        vals = list(struct.unpack('<' + str(n) + fmt, data[:n * size])) if n else []
        return (tc, vals)
    if tc == b'Y':
        return (b'i', struct.unpack('<h', f.read(2))[0])
    raise ValueError(f'unknown prop type {tc!r}')

def _read_node(f, version):
    hdr = f.read(13)
    if len(hdr) < 13:
        return None
    end_off, num_props, prop_len, name_len = struct.unpack('<IIIB', hdr)
    if end_off == 0 and num_props == 0 and prop_len == 0 and name_len == 0:
        return None  # null sentinel
    name = f.read(name_len).decode('utf-8', 'replace')
    if '\x00' in name:  # FBX "Name\x00\x01Class" compound naming
        name = name.split('\x00', 1)[0]
    node = Node(name)
    for _ in range(num_props):
        tc = f.read(1)
        node.props.append(_read_prop(f, tc))
    while f.tell() < end_off:
        child = _read_node(f, version)
        if child is None:
            break
        node.children.append(child)
    f.seek(end_off)
    return node

class FBX:
    def __init__(self):
        self.nodes = []        # top-level nodes
        self.objects = {}      # id -> (type, Node)
        self.connections = []  # (type, child, parent, prop)
        self.version = 0
    def by_type(self, typ):
        return [(oid, n) for oid, (t, n) in self.objects.items() if t == typ]
    def models(self):
        return [(oid, n) for oid, (t, n) in self.objects.items()
                if t == 'Model' and n.prop(2) in (b'Mesh', 'Mesh', None)]
    def children_of(self, model_id):
        out = []
        for (ct, ch, pa, pr) in self.connections:
            if ct == 'OO' and pa == model_id:
                t = self.objects.get(ch)
                if t and t[0] == 'Model':
                    out.append((ch, t[1]))
        return out
    def geometry_of(self, model_id):
        for (ct, ch, pa, pr) in self.connections:
            if ct == 'OO' and pa == model_id:
                t = self.objects.get(ch)
                if t and t[0] == 'Geometry':
                    return (ch, t[1])
        return None
    def materials_of(self, model_id):
        out = []
        for (ct, ch, pa, pr) in self.connections:
            if ct in ('OO', 'OP') and pa == model_id:
                t = self.objects.get(ch)
                if t and t[0] == 'Material':
                    out.append((ch, t[1]))
        return out
    def root_models(self):
        out = []
        for (ct, ch, pa, pr) in self.connections:
            if ct == 'OO' and pa == 0:
                t = self.objects.get(ch)
                if t and t[0] == 'Model':
                    out.append((ch, t[1]))
        return out

def parse(path):
    with open(path, 'rb') as f:
        data = f.read()
    if not data.startswith(FBX_MAGIC):
        raise ValueError(f'{path}: not a binary FBX')
    version = struct.unpack('<I', data[23:27])[0]
    fbx = FBX()
    fbx.version = version
    f = io.BytesIO(data)
    f.seek(27)
    while True:
        pos = f.tell()
        node = _read_node(f, version)
        if node is None:
            break
        fbx.nodes.append(node)
        if node.name == 'Objects':
            for obj in node.children:
                if obj.name in ('Model', 'Geometry', 'Material', 'Texture', 'Video', 'NodeAttribute'):
                    oid = obj.prop(0)
                    fbx.objects[oid] = (obj.name, obj)
        elif node.name == 'Connections':
            for c in node.children:
                if c.name == 'C':
                    ct = c.prop(0)
                    ch, pa = c.prop(1), c.prop(2)
                    pr = c.prop(3) if len(c.props) > 3 else None
                    fbx.connections.append((ct, ch, pa, pr))
        if f.tell() == pos:
            break
    return fbx

def p70(node, name):
    p70n = node.find('Properties70')
    if p70n is None: return None
    for p in p70n.children:
        if p.name == 'P' and p.prop(0) == name:
            return p.props[-1][1] if p.props else None
    return None

def p70v3(node, name):
    """读 P 节点的 vec3 值（props[4:7] 为 x/y/z，'d' 类型三元组）。
    与 p70 的区别：p70 对 vec3 只返回最后一个分量（历史 bug 行为，保留兼容）。"""
    p70n = node.find('Properties70')
    if p70n is None: return None
    for p in p70n.children:
        if p.name == 'P' and p.prop(0) == name and len(p.props) >= 7:
            return [p.props[4][1], p.props[5][1], p.props[6][1]]
    return None

def mesh_data(geo_node):
    out = {}
    verts = geo_node.find('Vertices')
    if verts is None or not verts.props:
        return None
    out['positions'] = verts.props[0][1]
    pvi = geo_node.find('PolygonVertexIndex')
    pvis = pvi.props[0][1] if pvi and pvi.props else []
    polys = []
    cur = []
    for idx in pvis:
        if idx < 0:
            cur.append(~idx)
            polys.append(cur)
            cur = []
        else:
            cur.append(idx)
    if cur: polys.append(cur)
    out['polys'] = polys
    len_node = geo_node.find('LayerElementNormal')
    if len_node:
        mv = len_node.find('MappingInformationType')
        vn = len_node.find('Normals')
        out['normals_raw'] = vn.props[0][1] if vn and vn.props else []
        out['normals_mapping'] = mv.prop(0) if mv else 'ByPolygonVertex'
    luv = None
    for c in geo_node.children:
        if c.name == 'LayerElementUV':
            luv = c; break
    if luv:
        mv = luv.find('MappingInformationType')
        uv = luv.find('UV')
        idxn = luv.find('UVIndex')
        out['uvs_raw'] = uv.props[0][1] if uv and uv.props else []
        out['uv_index'] = idxn.props[0][1] if idxn and idxn.props else None
        out['uvs_mapping'] = mv.prop(0) if mv else 'ByPolygonVertex'
    lem = geo_node.find('LayerElementMaterial')
    if lem:
        mv = lem.find('MappingInformationType')
        mi = lem.find('Materials')
        out['mat_mapping'] = mv.prop(0) if mv else 'AllSame'
        out['mat_indices'] = mi.props[0][1] if mi and mi.props else []
    return out

if __name__ == '__main__':
    fbx = parse(sys.argv[1])
    print(f'version={fbx.version} objects={len(fbx.objects)}')
    for oid, n in sorted(fbx.models(), key=lambda x: x[1].prop(1) or ''):
        geo = fbx.geometry_of(oid)
        tr = p70(n, 'Lcl Translation')
        sc = p70(n, 'Lcl Scaling')
        print(f'Model {n.prop(1)!r} id={oid} geo={"y" if geo else "-"} t={tr} s={sc}')
    for oid, n in fbx.by_type('Geometry'):
        md = mesh_data(n)
        if md:
            pos = md['positions']
            xs = pos[0::3]; ys = pos[1::3]; zs = pos[2::3]
            print(f'Geo id={oid} nv={len(xs)} np={len(md["polys"])} '
                  f'bbox=({min(xs):.4f},{min(ys):.4f},{min(zs):.4f})..({max(xs):.4f},{max(ys):.4f},{max(zs):.4f})')
    print('roots:', [n.prop(1) for _, n in fbx.root_models()])
    for oid, n in fbx.by_type('Material'):
        print('Material', n.prop(1))

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
from unity_yaml import UnityAssets, parse_prefab, scene_tree, parse_material, UNITY_ROOT, load_yaml_docs
from fbx_binary import parse as fbx_parse, mesh_data, p70

OUT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'build', 'assets'))
MIRROR_X = True

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


def trs_matrix(t, mirror_x=MIRROR_X, unit=1.0):
    """Node local matrix, with Unity->three.js conversion baked in.
    three.js = M * Unity where M mirrors X. So: p' = (-x, y, z); q' = mirror; s unaffected."""
    q = t['rotation']; p = t['position']; s = t['scale']
    # Mirror applied to quaternion: R' = S R S, S = diag(-1,1,1)
    # For q=(x,y,z,w): q' = (x, -y, -z, w)  [conjugate of q by S]
    if mirror_x:
        qx, qy, qz, qw = q
        q2 = [qx, -qy, -qz, qw]
        p = [-p[0]*unit, p[1]*unit, p[2]*unit]
    else:
        q2 = q
        p = [p[0]*unit, p[1]*unit, p[2]*unit]
    # quaternion to matrix (column-major math, output row-major for glTF)
    x, y, z, w = q2
    m = [1-2*(y*y+z*z), 2*(x*y+z*w), 2*(x*z-y*w), 0.0,
         2*(x*y-z*w), 1-2*(x*x+z*z), 2*(y*z+x*w), 0.0,
         2*(x*z+y*w), 2*(y*z-x*w), 1-2*(x*x+y*y), 0.0,
         p[0], p[1], p[2], 1.0]
    # apply scale
    for i in range(3):
        m[i*4+0] *= s[0]; m[i*4+1] *= s[1]; m[i*4+2] *= s[2]
    return m


def conv_pos(v, unit, mirror_x=MIRROR_X):
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
        info = {'fbx': f, 'unit': unit * 0.01, 'model_geos': {}, 'geo_by_fileid': {}}
        for i, (oid, n) in enumerate(f.by_type('Model')):
            geo = f.geometry_of(oid)
            if geo:
                objname = (n.prop(1) or n.name).split('\x00', 1)[0]
                info['model_geos'][objname] = geo
                info['geo_by_fileid'][4300000 + 2 * i] = geo
        self.cache[path] = info
        return info


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

    def emit_node(node, parent_children):
        comps = {c['class']: c['data'] for c in node['components']}
        mesh_idx = None
        mf = comps.get(33)  # MeshFilter
        mr = comps.get(23)  # MeshRenderer
        if mf and mr and node.get('active', 1):
            mesh_ref = mf.get('m_Mesh')
            if isinstance(mesh_ref, dict) and mesh_ref.get('guid'):
                fbx_path = ua.guid_map.get(mesh_ref['guid'])
                if fbx_path and fbx_path.lower().endswith('.fbx'):
                    info = fbx_cache_.get(fbx_path)
                    geo = info['geo_by_fileid'].get(mesh_ref.get('fileID'))
                    if geo is None:
                        geo = info['model_geos'].get(node['name'])
                    if geo is None and info['model_geos']:
                        geo = next(iter(info['model_geos'].values()))
                    if geo is not None:
                        md = mesh_data(geo[1])
                        if md:
                            mesh_idx = _emit_mesh(glb, node, md, info, mr, ua)
                            stats['meshes'] += 1
                            stats['verts'] += len(md['positions']) // 3
        node_idx = glb.add_node(node['name'] or 'node', mesh=mesh_idx,
                                 matrix=trs_matrix(node['transform']))
        parent_children.append(node_idx)
        child_root = glb.json['nodes'][node_idx].setdefault('children', [])
        for ch in node['children']:
            emit_node(ch, child_root)
        return node_idx

    root_children = glb.json['scenes'][0]['nodes']
    # root transform itself is identity for components; start at children of root
    for ch in root['children']:
        emit_node(ch, root_children)

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
            'name': go.get('m_Name', ''),
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
    p = tr.get('m_LocalPosition', {})
    v = [p.get('x', 0), p.get('y', 0), p.get('z', 0)]
    q = tr.get('m_LocalRotation', {})
    qq = [q.get('x', 0), q.get('y', 0), q.get('z', 0), q.get('w', 1)]
    s = tr.get('m_LocalScale', {})
    ss = [s.get('x', 1), s.get('y', 1), s.get('z', 1)]
    v = [v[i]*ss[i] for i in range(3)]
    # rotate then add parents
    father = tr.get('m_Father', {}).get('fileID')
    while father:
        ptr = pf['transforms'].get(father)
        if not ptr: break
        # rotate by parent quat (approx: full TRS)
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

def _emit_mesh(glb, node, md, info, mr, ua):
    """Emit an FBX mesh as glTF primitives with per-corner vertex expansion."""
    unit = info['unit']
    verts = md['positions']
    polys = md['polys']
    nm = md.get('normals_mapping', 'ByPolygonVertex')
    nr = md.get('normals_raw') or []
    um = md.get('uvs_mapping', 'ByPolygonVertex')
    ur = md.get('uvs_raw') or []
    uvi = md.get('uv_index')
    positions, normals, uvs, indices = [], [], [], []
    vc = 0
    corner = 0
    for poly in polys:
        if len(poly) < 3:
            corner += len(poly)
            continue
        for k, cx in enumerate(poly):
            positions.extend(conv_pos(verts[cx*3:cx*3+3], unit))
            if nr:
                if nm == 'ByPolygonVertex': bi = (corner + k) * 3
                elif nm == 'ByVertice': bi = cx * 3
                else: bi = 0
                if bi < len(nr):
                    normals.extend(conv_normal(nr[bi:bi+3]))
            if ur:
                if uvi is not None and (corner + k) < len(uvi):
                    ui = uvi[corner + k] * 2
                elif um == 'ByVertice':
                    ui = cx * 2
                else:
                    ui = (corner + k) * 2
                if ui + 1 < len(ur):
                    uvs.extend([ur[ui], 1.0 - ur[ui+1]])
            vc += 1
        for k in range(1, len(poly) - 1):
            indices.extend([vc - len(poly), vc - len(poly) + k, vc - len(poly) + k + 1])
        corner += len(poly)
    if MIRROR_X:
        indices = flip_winding(indices)
    if not normals:
        normals = _face_normals(positions, indices)
    # material
    matidx = None
    mats = mr.get('m_Materials') or []
    if mats:
        m0 = mats[0]
        if isinstance(m0, dict) and m0.get('guid'):
            mat_path = ua.guid_map.get(m0['guid'])
            if mat_path and mat_path.endswith('.mat'):
                mat = parse_material(os.path.join(UNITY_ROOT, mat_path))
                mat['name'] = os.path.splitext(os.path.basename(mat_path))[0]
                if mat.get('maintex'):
                    mat['maintex_path'] = ua.guid_map.get(mat['maintex'])
                matidx = glb.add_material(mat)
    if matidx is None:
        matidx = glb.add_material({'name': 'default'})
    return glb.add_mesh(node['name'], positions, normals, uvs, indices, matidx)

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
    print(f'\nTotal {len(catalog)} components -> {exp_dir}')

if __name__ == '__main__':
    main()

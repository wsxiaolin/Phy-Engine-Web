#!/usr/bin/env python3
"""Unity YAML asset parsing utilities: documents, prefabs, materials, GUID map."""
import os, re, sys, json, glob
import yaml

UNITY_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'unity'))

def load_yaml_docs(path):
    """Parse a Unity serialized file into a list of (classid, fileid, dict)."""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    if not text.startswith('%YAML'):
        return []
    docs = []
    parts = re.split(r'^--- !u!(\d+) &(\d+)\s*$', text, flags=re.M)
    # parts: [pre, classid, fileid, body, classid, fileid, body, ...]
    for i in range(1, len(parts), 3):
        classid = int(parts[i]); fileid = int(parts[i + 1]); body = parts[i + 2]
        try:
            data = yaml.safe_load(body)
        except Exception as e:
            data = {}
        # Unity wraps each doc body in its class name: {'GameObject': {...}}
        if isinstance(data, dict) and len(data) == 1:
            inner = next(iter(data.values()))
            if isinstance(inner, dict):
                data = inner
        docs.append((classid, fileid, data if isinstance(data, dict) else {}))
    return docs

class UnityAssets:
    def __init__(self, root=UNITY_ROOT):
        self.root = root
        self.guid_map = {}     # guid -> asset path (relative, no ext meta)
        self.path_map = {}     # rel path -> guid
        self._build()
    def _build(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            if '.git' in dirpath: continue
            for fn in filenames:
                if not fn.endswith('.meta'): continue
                full = os.path.join(dirpath, fn)
                asset = full[:-5]
                rel = os.path.relpath(asset, self.root)
                try:
                    with open(full, 'r', encoding='utf-8', errors='replace') as f:
                        head = f.read(400)
                except Exception:
                    continue
                m = re.search(r'guid:\s*([0-9a-f]{32})', head)
                if m:
                    self.guid_map[m.group(1)] = rel
                    self.path_map[rel] = m.group(1)
    def resolve(self, guid, fileid=0):
        """guid(+fileid) -> (path, type_hint). fileid 4300000+=mesh, else main asset."""
        return self.guid_map.get(guid)

def ref(value):
    """Unity fileID reference dict -> (fileid, guid, type) or None."""
    if not isinstance(value, dict): return None
    return (value.get('fileID', 0), value.get('guid', ''), value.get('type', 0))

def parse_prefab(path):
    docs = load_yaml_docs(path)
    gameobjects = {}   # fileid -> go dict
    transforms = {}    # fileid -> transform dict
    components = {}    # fileid -> (classid, comp dict)
    monobehaviours = {}
    for (classid, fileid, data) in docs:
        if classid == 1:
            gameobjects[fileid] = data
        elif classid == 4:
            transforms[fileid] = data
        elif classid == 114:
            monobehaviours[fileid] = data
        else:
            components[fileid] = (classid, data)
    # index components by owner gameobject
    go_comps = {}
    for fid, mb in monobehaviours.items():
        go = mb.get('m_GameObject')
        if isinstance(go, dict):
            goid = go.get('fileID', 0)
            go_comps.setdefault(goid, []).append((114, fid, mb))
    for fid, (cid, data) in components.items():
        go = data.get('m_GameObject')
        if isinstance(go, dict):
            goid = go.get('fileID', 0)
            go_comps.setdefault(goid, []).append((cid, fid, data))
    return {'gameobjects': gameobjects, 'transforms': transforms,
            'components': components, 'monobehaviours': monobehaviours,
            'go_comps': go_comps, 'docs': docs}

def safe_name(v):
    """m_Name 防御：PyYAML 1.1 会把裸 On/Off/Yes/No/True/False 解析成布尔，
    导致 GLB 节点名变成 true/false → three.js GLTFLoader sanitizeNodeName 崩溃
    （Air_Switch.glb 曾因此炸掉批量截图）。按 Unity 常见命名还原首字母大写形式。"""
    if isinstance(v, bool):
        return 'On' if v else 'Off'
    if v is None:
        return ''
    return v if isinstance(v, str) else str(v)

def scene_tree(pf, root_fileid=None):
    """Build scene-graph tree from parsed prefab: nodes with transform + components."""
    transforms = pf['transforms']
    gameobjects = pf['gameobjects']
    # find roots: transforms with father == 0
    children_index = {}
    for fid, tr in transforms.items():
        father = tr.get('m_Father')
        ffid = father.get('fileID', 0) if isinstance(father, dict) else 0
        children_index.setdefault(ffid, []).append(fid)
    roots = children_index.get(0, [])
    if root_fileid is not None:
        roots = [root_fileid]

    def build(fid):
        tr = transforms.get(fid)
        if tr is None: return None
        go_ref = tr.get('m_GameObject')
        goid = go_ref.get('fileID', 0) if isinstance(go_ref, dict) else 0
        go = gameobjects.get(goid, {})
        comps = pf['go_comps'].get(goid, [])
        node = {
            'name': safe_name(go.get('m_Name', '')),
            'active': go.get('m_IsActive', 1),
            'transform': _read_transform(tr),
            'components': [],
            'children': []
        }
        child_ids = []
        for c in tr.get('m_Children', []) or []:
            child_ids.append(c.get('fileID', 0) if isinstance(c, dict) else c)
        node['children'] = [build(c) for c in child_ids if c]
        node['children'] = [c for c in node['children'] if c]
        for (cid, fid2, data) in comps:
            node['components'].append({'class': cid, 'fileID': fid2, 'data': data})
        return node

    return [build(r) for r in roots if build(r)]

def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def _read_transform(tr):
    q = tr.get('m_LocalRotation', {})
    p = tr.get('m_LocalPosition', {})
    s = tr.get('m_LocalScale', {})
    return {
        'rotation': [_num(q.get('x', 0)), _num(q.get('y', 0)), _num(q.get('z', 0)), _num(q.get('w', 1))],
        'position': [_num(p.get('x', 0)), _num(p.get('y', 0)), _num(p.get('z', 0))],
        'scale': [_num(s.get('x', 1), 1), _num(s.get('y', 1), 1), _num(s.get('z', 1), 1)],
    }

def _entries(seq):
    """Normalize Unity YAML list fields (m_TexEnvs etc.) to [{key, val}].
    PyYAML yields single-key dicts like [{'_MainTex': {...}}]; some files may
    contain [key, val] pairs instead."""
    out = []
    for entry in seq or []:
        if isinstance(entry, dict) and len(entry) >= 1:
            k = next(iter(entry))
            out.append({'key': k, 'val': entry[k] if isinstance(entry[k], dict) else entry[k]})
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            out.append({'key': entry[0], 'val': entry[1] if isinstance(entry[1], dict) else entry[1]})
    return out

def parse_material(path):
    """Extract shader + standard material props from a .mat file."""
    docs = load_yaml_docs(path)
    out = {'shader': None, 'color': None, 'maintex': None, 'bump': None,
           'metallic': None, 'smoothness': None, 'emission': None, 'emissionColor': None,
           'mode': 'opaque', 'srcBlend': None, 'dstBlend': None, 'renderQueue': None}
    for (cid, fid, data) in docs:
        if data.get('m_Shader'):
            sh = data['m_Shader']
            out['shader'] = sh.get('guid', '')
        if 'm_SavedProperties' in data:
            sp = data['m_SavedProperties']
            for entry in _entries(sp.get('m_TexEnvs')):
                key, val = entry['key'], entry['val']
                if not isinstance(val, dict):
                    continue
                if key == '_MainTex':
                    mtl = val.get('m_Texture')
                    if isinstance(mtl, dict) and mtl.get('guid'):
                        out['maintex'] = mtl['guid']
                elif key == '_BumpMap':
                    mtl = val.get('m_Texture')
                    if isinstance(mtl, dict) and mtl.get('guid'):
                        out['bump'] = mtl['guid']
                elif key == '_EmissionMap':
                    mtl = val.get('m_Texture')
                    if isinstance(mtl, dict) and mtl.get('guid'):
                        out['emissionMap'] = mtl['guid']
            for entry in _entries(sp.get('m_Floats')):
                key, val = entry['key'], entry['val']
                if key == '_Metallic': out['metallic'] = val
                elif key == '_Glossiness': out['smoothness'] = val
                elif key == '_Mode': out['mode'] = {0:'opaque',1:'cutout',2:'fade',3:'transparent'}.get(val, 'opaque')
                elif key == '_SrcBlend': out['srcBlend'] = val
                elif key == '_DstBlend': out['dstBlend'] = val
                elif key == '_Cutoff': out['cutoff'] = val
            for entry in _entries(sp.get('m_Colors')):
                key, val = entry['key'], entry['val']
                if not isinstance(val, dict):
                    continue
                if key == '_Color':
                    out['color'] = [val.get('r', 1), val.get('g', 1), val.get('b', 1), val.get('a', 1)]
                elif key == '_EmissionColor':
                    out['emissionColor'] = [val.get('r', 0), val.get('g', 0), val.get('b', 0), val.get('a', 1)]
    out['renderQueue'] = None
    for (cid, fid, data) in docs:
        if isinstance(data.get('m_CustomRenderQueue'), int):
            out['renderQueue'] = data['m_CustomRenderQueue']
    return out

def find_component_script_names(pf, script_guid_map):
    """Map script GUIDs to file paths (needs GUID of CircuitComponent etc.)."""
    out = {}
    for fid, mb in pf['monobehaviours'].items():
        sh = mb.get('m_Script')
        if isinstance(sh, dict) and sh.get('guid'):
            out[fid] = script_guid_map.get(sh['guid'], sh['guid'])
    return out

if __name__ == '__main__':
    ua = UnityAssets()
    print('assets:', len(ua.guid_map))
    pf = parse_prefab(os.path.join(UNITY_ROOT, 'Assets/Resources/Experiments/Basic Circuits/Resistor.prefab'))
    tree = scene_tree(pf)
    def dump(n, d=0):
        print('  ' * d + f"{n['name']} pos={n['transform']['position']} scale={n['transform']['scale'][:2]} comps={[c['class'] for c in n['components']]}")
        for c in n['children']: dump(c, d + 1)
    for r in tree: dump(r)

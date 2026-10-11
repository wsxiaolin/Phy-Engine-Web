#!/usr/bin/env python3
"""Regenerate catalog.json pin positions with CORRECT prefab math.

Old bug: _world_pos in extract_components.py (1) never applied ancestor
scales and (2) applied the node's own scale to its own position, so nested
hierarchies exploded (Galvanometer pins at -5.15 m) and simple ones drifted
(Battery 0.06 -> 0.0634). This script recomputes every pin by composing the
full ancestor chain S,R,T and mirroring x into GLB space — verified equal to
the GLB node matrices (Battery: +-0.06 exactly). Unity WireManager attaches
wires at Pin.WirePosition when that child exists, so prefer it.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
CAT = os.path.join(ROOT, 'build', 'assets', 'catalog.json')

sys.path.insert(0, HERE)
from unity_yaml import UnityAssets, UNITY_ROOT, parse_prefab  # noqa: E402


def qrot(q, v):
    x, y, z = v
    qx, qy, qz, qw = q
    t = [qw*x + qy*z - qz*y, qw*y + qz*x - qx*z, qw*z + qx*y - qy*x]
    return [x + 2*(qy*t[2]-qz*t[1]), y + 2*(qz*t[0]-qx*t[2]), z + 2*(qx*t[1]-qy*t[0])]


def world_of(transforms, tr, mirror=True):
    p = tr.get('m_LocalPosition', {})
    v = [p.get('x', 0), p.get('y', 0), p.get('z', 0)]
    father = tr.get('m_Father', {}).get('fileID')
    while father:
        a = transforms.get(father)
        if not a:
            break
        s = a.get('m_LocalScale', {})
        v = [v[i]*s.get('xyz'[i], 1) for i in range(3)]
        q = a.get('m_LocalRotation', {})
        v = qrot([q.get('x', 0), q.get('y', 0), q.get('z', 0), q.get('w', 1)], v)
        pp = a.get('m_LocalPosition', {})
        v = [v[0]+pp.get('x', 0), v[1]+pp.get('y', 0), v[2]+pp.get('z', 0)]
        father = a.get('m_Father', {}).get('fileID')
    if mirror:
        v[0] = -v[0]
    return v


def find_prefab(model_id):
    # ModelID 与文件名的已知差异（Unity 资产命名不统一）
    alias = {
        'And Gate': 'And-Gate', 'Or Gate': 'Or-Gate', 'No Gate': 'No-Gate',
        'Yes Gate': 'Yes-Gate', 'Xor Gate': 'Xor-Gate', 'Xnor Gate': 'Xnor-Gate',
        'Nand Gate': 'Nand-Gate', 'Nor Gate': 'Nor-Gate', 'Imp Gate': 'Imp-Gate',
        'Nimp Gate': 'Nimp-Gate', 'Relay Component': 'Relay Element',
        'Simple Ammeter': 'Ammeter', 'Simple Voltmeter': 'Voltmeter',
        'Photodiode': 'Photo Diode', 'Photoresistor': 'Photo Resistor',
        'Rectifier': 'Recticifier',  # Unity 资产拼写错误，照抄
    }
    target = alias.get(model_id, model_id) + '.prefab'
    for root, dirs, files in os.walk(os.path.join(UNITY_ROOT, 'Assets/Resources/Experiments')):
        if target in files:
            return os.path.join(root, target)
    # 兜底：空间↔横杠互换再试
    alt = alias.get(model_id, model_id).replace('-', ' ') + '.prefab'
    for root, dirs, files in os.walk(os.path.join(UNITY_ROOT, 'Assets/Resources/Experiments')):
        if alt in files:
            return os.path.join(root, alt)
    return None


def main():
    cat = json.load(open(CAT))
    changed = ok = warn = 0
    for entry in cat:
        pins = entry.get('pins') or []
        if not pins:
            continue
        pf_path = find_prefab(entry['ModelID'])
        if not pf_path:
            print(f"WARN prefab not found: {entry['ModelID']}")
            warn += len(pins)
            continue
        pf = parse_prefab(pf_path)
        gos = {fid: g.get('m_Name', '?') for fid, g in pf['gameobjects'].items()}
        transforms = pf['transforms']
        # 找含 Pins 数组的 CircuitComponent MB
        pins_mb = next((mb for mb in pf['monobehaviours'].values()
                        if isinstance(mb, dict) and isinstance(mb.get('Pins'), list) and mb['Pins']), None)
        if pins_mb is None:
            print(f"WARN no Pins MB: {entry['ModelID']}")
            warn += len(pins)
            continue
        for i, p in enumerate(pins):
            if i >= len(pins_mb['Pins']):
                print(f"WARN {entry['ModelID']} pin[{i}] beyond prefab Pins")
                warn += 1
                continue
            go_id = pins_mb['Pins'][i].get('fileID')
            pmb = pf['monobehaviours'].get(go_id)
            if not pmb:
                warn += 1
                continue
            pgo = pmb.get('m_GameObject', {}).get('fileID')
            pin_fid = next((fid for fid, t in transforms.items()
                            if t.get('m_GameObject', {}).get('fileID') == pgo), None)
            if not pin_fid:
                warn += 1
                continue
            # Unity 导线端点优先 WirePosition 子物体
            wp_fid = next((fid for fid, t in transforms.items()
                           if t.get('m_Father', {}).get('fileID') == pin_fid
                           and gos.get(t.get('m_GameObject', {}).get('fileID'), '') == 'WirePosition'), None)
            src_tr = transforms[wp_fid] if wp_fid else transforms[pin_fid]
            newpos = world_of(transforms, src_tr)
            old = p.get('position', [1e9, 1e9, 1e9])
            if max(abs(old[k]-newpos[k]) for k in range(3)) > 1e-6:
                changed += 1
                if changed <= 14:
                    print(f"  {entry['ModelID']:<26} {p.get('name','?'):<14} "
                          f"({old[0]:+.4f},{old[1]:+.4f},{old[2]:+.4f}) -> "
                          f"({newpos[0]:+.4f},{newpos[1]:+.4f},{newpos[2]:+.4f})")
            else:
                ok += 1
            p['position'] = [round(newpos[0], 6), round(newpos[1], 6), round(newpos[2], 6)]
    json.dump(cat, open(CAT, 'w'), ensure_ascii=False, indent=1)
    print(f'changed={changed} ok={ok} warn={warn}')


if __name__ == '__main__':
    main()

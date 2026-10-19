#!/usr/bin/env python3
"""解析 Unity 实验 prefab 中 Pin 对象的位置/缩放，供接线柱对照。"""
import re, sys

path = sys.argv[1] if len(sys.argv) > 1 else 'Assets/Resources/Experiments/Analog Circuits/Transformer.prefab'
txt = open(path, encoding='utf-8').read()

gos, transforms, others = {}, {}, {}
for b in re.split(r'--- !u!\d+ &', txt)[1:]:
    parts = b.split('\n', 2)
    fid = parts[0].strip()
    kind = parts[1].strip().rstrip(':') if len(parts) > 1 else ''
    body = parts[2] if len(parts) > 2 else ''
    if kind == 'GameObject':
        m = re.search(r'm_Name: (.+)', body)
        gos[fid] = m.group(1) if m else '?'
    elif kind == 'Transform':
        gm = re.search(r'm_GameObject: \{fileID: (\d+)\}', body)
        pm = re.search(r'm_LocalPosition: \{x: ([-\d.e]+), y: ([-\d.e]+), z: ([-\d.e]+)\}', body)
        sm = re.search(r'm_LocalScale: \{x: ([-\d.e]+), y: ([-\d.e]+), z: ([-\d.e]+)\}', body)
        fm = re.search(r'm_Father: \{fileID: (\d+)\}', body)
        transforms[fid] = {
            'go': gm.group(1) if gm else '?',
            'pos': pm.groups() if pm else None,
            'scale': sm.groups() if sm else None,
            'father': fm.group(1) if fm else '?',
        }

go_by_transform = {t['go']: (fid, t) for fid, t in transforms.items()}

for fid, name in gos.items():
    if 'Pin' not in name:
        continue
    tf = go_by_transform.get(fid)
    if not tf:
        continue
    tid, t = tf
    print(f'== {name} (go {fid}, transform {tid})')
    print(f'   pos  = {t["pos"]}')
    print(f'   scale= {t["scale"]}')
    # 逐级向上打印父链
    father = t['father']
    depth = 0
    while father != '0' and depth < 8:
        ft = transforms.get(father)
        if not ft:
            break
        fname = gos.get(ft['go'], '?')
        print(f'   <- parent {fname} pos={ft["pos"]} scale={ft["scale"]}')
        father = ft['father']
        depth += 1

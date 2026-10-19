#!/usr/bin/env python3
"""geo_diff.py — 对比 HEAD(baked) vs 工作区(nobake) GLB 的真实几何差异。
忽略字节顺序噪声：每 mesh POSITION 顶点排序后 hash + 节点树全局 TRS 指纹。
输出：哪些元件几何真变了（需要重截图+重对照），哪些只是二进制噪声。"""
import struct, json, hashlib, subprocess, sys, os, tempfile

def load(path):
    data = open(path, 'rb').read()
    magic, ver, total = struct.unpack('<III', data[:12])
    assert magic == 0x46546C67, f'not GLB: {path}'
    off = 12; doc = None; binchunk = b''
    while off < total:
        clen, ctype = struct.unpack('<II', data[off:off+8])
        chunk = data[off+8:off+8+clen]
        if ctype == 0x4E4F534A: doc = json.loads(chunk)
        if ctype == 0x004E4942: binchunk = chunk
        off += 8 + clen
    return doc, binchunk

def geo_fingerprint(doc, binchunk):
    """几何指纹：每 mesh 的 (排序顶点 tuple hash, 顶点数, 图元材质序列) + 节点全局矩阵。"""
    fps = []
    def node_matrix(n):
        if 'matrix' in n:
            m = tuple(round(float(v), 6) for v in n['matrix'])
        else:
            t = n.get('translation', [0,0,0]); r = n.get('rotation', [0,0,0,1]); s = n.get('scale', [1,1,1])
            m = tuple(round(float(v), 6) for v in (tuple(t)+tuple(r)+tuple(s)))
        return m
    def walk(idx, depth, parent_m):
        n = doc['nodes'][idx]
        m = node_matrix(n)
        fp = []
        if 'mesh' in n:
            mesh = doc['meshes'][n['mesh']]
            for pi, p in enumerate(mesh.get('primitives', [])):
                pos_acc = p.get('attributes', {}).get('POSITION')
                if pos_acc is None: continue
                acc = doc['accessors'][pos_acc]
                bo = acc.get('bufferView'); c = acc.get('byteOffset', 0)
                comp = acc.get('componentType', 5126); ct = acc.get('count', 0)
                bv = doc['bufferViews'][bo]
                base = bv.get('byteOffset', 0) + c
                sz = 4 if comp == 5126 else 2
                stride = bv.get('byteStride') or sz*3
                pts = []
                for k in range(ct):
                    o = base + k*stride
                    x, y, z = struct.unpack_from('<3f' if comp==5126 else '<3e', binchunk, o)
                    pts.append((round(x,5), round(y,5), round(z,5)))
                ph = hashlib.md5(repr(sorted(pts)).encode()).hexdigest()[:10]
                fp.append((ph, ct, p.get('material')))
            fps.append((n.get('name','?'), m, tuple(fp)))
        for ch in n.get('children', []):
            walk(ch, depth+1, m)
    walk(0, 0, None)
    return tuple(fps)

ROOT = '/home/z/my-project/phy-engine-web'
os.chdir(ROOT)
comps = sorted(os.listdir('build/assets/components'))
changed, same, errors = [], [], []
tmp = tempfile.mkdtemp()
for i, fn in enumerate(comps):
    if not fn.endswith('.glb'): continue
    name = fn[:-4]
    path = f'build/assets/components/{fn}'
    # HEAD 版（LFS smudge）
    try:
        r = subprocess.run(['bash','-c', f'git show HEAD:build/assets/components/{fn} | git lfs smudge'],
                          capture_output=True)
        if r.returncode != 0 or len(r.stdout) < 100:
            errors.append((name, 'head fetch fail')); continue
        hp = os.path.join(tmp, 'head.glb')
        open(hp,'wb').write(r.stdout)
        j1, b1 = load(hp)
        j2, b2 = load(path)
        f1, f2 = geo_fingerprint(j1, b1), geo_fingerprint(j2, b2)
        if f1 == f2: same.append(name)
        else: changed.append(name)
    except Exception as e:
        errors.append((name, str(e)[:80]))
    if (i+1) % 20 == 0: print(f'  ...{i+1}/{len(comps)}', flush=True)

print(f'\n=== 几何真变 {len(changed)} ===')
print(' '.join(changed))
print(f'=== 几何相同(仅字节噪声) {len(same)} ===')
print(' '.join(same))
if errors:
    print(f'=== 错误 {len(errors)} ===')
    for n, e in errors: print(f'  {n}: {e}')

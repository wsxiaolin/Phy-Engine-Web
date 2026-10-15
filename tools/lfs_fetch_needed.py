#!/usr/bin/env python3
"""Fetch LFS objects for the given pointer list via Batch API; report availability.

Expects a pointer list JSON at /tmp/need_list.json (list of [path, oid, size],
as produced by scanning GLB/LFS pointers during the audit workflow). For a
self-contained full materialization prefer lfs_batch_fetch.py."""
import os, json, time, base64, hashlib
import urllib.request, concurrent.futures

UNITY = '/home/z/my-project/phy-engine-web/unity'
LFS_CACHE = os.path.join(UNITY, '.git', 'lfs', 'objects')
BATCH_URL = 'https://github.com/NetLogo-Mobile/Physics-Lab.git/info/lfs/objects/batch'
TOKEN = open('/home/z/.gh-token-pltown').read().strip()
AUTH = 'Basic ' + base64.b64encode(f'wsxiaolin:{TOKEN}'.encode()).decode()

need = json.load(open('/tmp/need_list.json'))
oid2size = {}
oid2paths = {}
for p, oid, size in need:
    oid2size[oid] = size
    oid2paths.setdefault(oid, []).append(p)
print(f'pointers={len(need)} unique={len(oid2size)}', flush=True)

def batch_api(objs):
    req = urllib.request.Request(BATCH_URL,
        data=json.dumps({"operation": "download", "transfer": "basic",
                         "objects": [{"oid": o, "size": s} for o, s in objs],
                         "ref": {"name": "refs/heads/2.0"}}).encode(),
        headers={'Authorization': AUTH, 'Content-Type': 'application/json',
                 'Accept': 'application/vnd.git-lfs+json'})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())

def cache_path(oid):
    return os.path.join(LFS_CACHE, oid[:2], oid[2:4], oid)

def download(oid, href):
    cp = cache_path(oid)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    req = urllib.request.Request(href, headers={'Authorization': AUTH})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    if hashlib.sha256(data).hexdigest() != oid:
        raise ValueError(f'sha mismatch {oid[:12]}')
    with open(cp, 'wb') as f:
        f.write(data)
    return len(data)

oids = list(oid2size.items())
have, miss, dls = 0, [], []
for i in range(0, len(oids), 80):
    chunk = oids[i:i+80]
    resp = None
    for att in range(3):
        try:
            resp = batch_api(chunk); break
        except Exception as e:
            print(f'retry {i}: {e}', flush=True); time.sleep(3)
    if resp is None:
        miss.extend(o for o, _ in chunk); continue
    for o in resp.get('objects', []):
        if o.get('error'):
            miss.append(o['oid']); continue
        a = o.get('actions', {}).get('download')
        if not a:
            miss.append(o['oid']); continue
        dls.append((o['oid'], a['href'], o.get('size', 0)))
print(f'available={len(dls)} server-missing={len(miss)}', flush=True)

ok = 0
def _dl(item):
    oid, href, _ = item
    for att in range(4):
        try:
            return download(oid, href)
        except Exception as e:
            time.sleep(2)
    raise ValueError(f'dl fail {oid[:12]}')

with concurrent.futures.ThreadPoolExecutor(6) as ex:
    futs = {ex.submit(_dl, d): d[0] for d in dls}
    for fu in concurrent.futures.as_completed(futs):
        try:
            fu.result(); ok += 1
        except Exception as e:
            print(f'DLFAIL {futs[fu][:12]}: {e}', flush=True)
print(f'downloaded={ok}/{len(dls)}', flush=True)

# copy out to workspace
copied = 0
for oid in list(oid2size):
    cp = cache_path(oid)
    if os.path.exists(cp) and os.path.getsize(cp) == oid2size[oid]:
        for p in oid2paths[oid]:
            with open(cp, 'rb') as f:
                data = f.read()
            with open(p, 'wb') as f:
                f.write(data)
            copied += 1
print(f'copied_to_workspace={copied}', flush=True)
miss_set = set(miss)
with open('/tmp/lfs_missing.json', 'w') as f:
    json.dump({o: oid2paths[o] for o in miss_set}, f, ensure_ascii=False, indent=1)
print('server_missing_paths:', flush=True)
for o in list(miss_set)[:40]:
    for p in oid2paths[o]:
        print('  MISS', p.replace(UNITY + '/', ''), flush=True)

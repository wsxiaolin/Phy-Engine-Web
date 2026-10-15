#!/usr/bin/env python3
"""Materialize all Git LFS pointer files under unity/ via GitHub LFS Batch API."""
import os, sys, json, time, base64, hashlib
import urllib.request, concurrent.futures

UNITY = '/home/z/my-project/phy-engine-web/unity'
LFS_CACHE = os.path.join(UNITY, '.git', 'lfs', 'objects')
BATCH_URL = 'https://github.com/NetLogo-Mobile/Physics-Lab.git/info/lfs/objects/batch'
MAGIC = b'version https://git-lfs.github.com/spec/v1'
TOKEN = open('/home/z/.gh-token-pltown').read().strip()
AUTH = 'Basic ' + base64.b64encode(f'wsxiaolin:{TOKEN}'.encode()).decode()

def scan_pointers():
    out = []  # (path, oid, size)
    for dp, dn, fn in os.walk(UNITY):
        if '.git' in dp.split(os.sep):
            continue
        for f in fn:
            p = os.path.join(dp, f)
            try:
                if os.path.getsize(p) > 300:
                    continue
                with open(p, 'rb') as fh:
                    head = fh.read(60)
                if not head.startswith(MAGIC):
                    continue
                with open(p, 'rb') as fh:
                    txt = fh.read().decode('utf-8', 'replace')
                oid = size = None
                for line in txt.splitlines():
                    if line.startswith('oid sha256:'):
                        oid = line[11:].strip()
                    elif line.startswith('size '):
                        size = int(line[5:].strip())
                if oid and size is not None:
                    out.append((p, oid, size))
            except Exception:
                pass
    return out

def batch_api(objs):
    req = urllib.request.Request(BATCH_URL,
        data=json.dumps({"operation": "download", "transfer": "basic",
                         "objects": [{"oid": o, "size": s} for o, s in objs],
                         "ref": {"name": "refs/heads/2.0"}}).encode(),
        headers={'Authorization': AUTH, 'Content-Type': 'application/json',
                 'Accept': 'application/vnd.git-lfs+json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def cache_path(oid):
    return os.path.join(LFS_CACHE, oid[:2], oid[2:4], oid)

def download(oid, href):
    cp = cache_path(oid)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    req = urllib.request.Request(href, headers={'Authorization': AUTH})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    # verify sha256
    if hashlib.sha256(data).hexdigest() != oid:
        raise ValueError(f'sha mismatch {oid}')
    with open(cp, 'wb') as f:
        f.write(data)
    return len(data)

def main():
    ptrs = scan_pointers()
    print(f'pointers: {len(ptrs)}', flush=True)
    # dedupe by oid
    oid2size = {}
    for p, oid, size in ptrs:
        oid2size.setdefault(oid, size)
    print(f'unique oids: {len(oid2size)}', flush=True)
    # check local cache first
    need = []
    for oid, size in oid2size.items():
        cp = cache_path(oid)
        if os.path.exists(cp) and os.path.getsize(cp) == size:
            continue
        need.append((oid, size))
    print(f'need download: {len(need)}', flush=True)
    # batch in chunks of 100
    ok = fail = 0
    for i in range(0, len(need), 100):
        chunk = need[i:i+100]
        for attempt in range(3):
            try:
                resp = batch_api([(o, s) for o, s in chunk])
                break
            except Exception as e:
                print(f'batch retry {i}: {e}', flush=True)
                time.sleep(3)
        else:
            continue
        dls = []
        for o in resp.get('objects', []):
            if 'error' in o and o['error']:
                print(f'ERR batch: {o["oid"][:12]} {o["error"]}', flush=True)
                fail += 1
                continue
            a = o.get('actions', {}).get('download')
            if not a:
                fail += 1
                continue
            dls.append((o['oid'], a['href']))
        def _dl(item):
            oid, href = item
            for att in range(3):
                try:
                    return download(oid, href)
                except Exception as e:
                    time.sleep(2)
            raise ValueError(f'download fail {oid}')
        with concurrent.futures.ThreadPoolExecutor(8) as ex:
            for n in ex.map(_dl, dls):
                ok += 1
        print(f'progress: {ok}/{len(need)}', flush=True)
    # copy from cache to workspace
    copied = 0
    for p, oid, size in ptrs:
        cp = cache_path(oid)
        if os.path.exists(cp) and os.path.getsize(cp) == size:
            with open(cp, 'rb') as f:
                data = f.read()
            with open(p, 'wb') as f:
                f.write(data)
            copied += 1
        else:
            print(f'STILL MISSING: {p} ({oid[:12]})', flush=True)
    print(f'DONE copied={copied}/{len(ptrs)} failed_oids={fail}', flush=True)

if __name__ == '__main__':
    main()

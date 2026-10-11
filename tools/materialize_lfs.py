import os, sys

ROOT = '/home/z/my-project/phy-engine-web/unity'
LFS_DIR = os.path.join(ROOT, '.git/lfs/objects')
POINTER_MAGIC = b'version https://git-lfs.github.com/spec/v1'

copied, missing, skipped = 0, 0, 0
missing_list = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    if '.git' in dirpath.split(os.sep):
        continue
    for fn in filenames:
        p = os.path.join(dirpath, fn)
        try:
            if os.path.getsize(p) > 200:
                continue
            with open(p, 'rb') as f:
                head = f.read(60)
            if not head.startswith(POINTER_MAGIC):
                continue
            # parse oid
            with open(p, 'rb') as f:
                content = f.read()
            oid = None
            for line in content.split(b'\n'):
                if line.startswith(b'oid sha256:'):
                    oid = line[len(b'oid sha256:'):].decode()
            if not oid:
                continue
            obj = os.path.join(LFS_DIR, oid[:2], oid[2:4], oid)
            if os.path.exists(obj):
                if os.path.getsize(obj) > 0:
                    shutil_copy(obj, p) if False else None
                    import shutil
                    shutil.copyfile(obj, p)
                    copied += 1
                else:
                    missing += 1
                    missing_list.append(p)
            else:
                missing += 1
                missing_list.append(p)
        except Exception as e:
            pass
print(f'copied={copied} missing={missing} skipped={skipped}')
for m in missing_list[:20]:
    print('MISSING:', m)

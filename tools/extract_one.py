#!/usr/bin/env python3
"""extract_one.py — 单件/多件实验提取（不动 build/assets 主产物）。
用法: python3 tools/extract_one.py <OutDir> "Prefab1" ["Prefab2" ...]
受 BAKE_FBX_M 环境开关控制（默认 1=烘）。
"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(__file__))
from unity_yaml import UnityAssets, UNITY_ROOT
import extract_components as ec

def main():
    out_dir = sys.argv[1]
    names = sys.argv[2:]
    os.makedirs(out_dir, exist_ok=True)
    ua = UnityAssets()
    fbx_cache = ec.FBXCache()
    catalog = []
    for nm in names:
        hits = glob.glob(os.path.join(UNITY_ROOT, 'Assets/Resources/Experiments/**', nm + '.prefab'), recursive=True)
        if not hits:
            print('MISS', nm); continue
        try:
            entry = ec.extract_component(hits[0], ua, fbx_cache, out_dir)
            if entry:
                catalog.append(entry)
                print(f"OK {entry['ModelID']} glb={entry['glbBytes']}B pins={len(entry['pins'])}")
            else:
                print('SKIP', nm)
        except Exception as e:
            import traceback; traceback.print_exc()
            print('ERR', nm, e)
    print('BAKE_FBX_M =', ec.BAKE_FBX_M, '->', out_dir)

if __name__ == '__main__':
    main()

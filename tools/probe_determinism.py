#!/usr/bin/env python3
"""probe_determinism.py — 提取链非确定性悬案的决定性实验探针（2026-10-23）.

背景（HANDOVER §0 P2）：跨会话两次提取同一 prefab，FBX 层读出的 SwPole/Pole
旋转列符号相反；同进程 3 连跑 md5 一致。静态审计（本日）结论：解析链纯确定
（字节流顺序解析 + dict 保序 + set 仅防环 + 纯浮点），唯一变量入口 = 环境开关
MIRROR_FIX / BAKE_FBX_M / KEEP_PIN_MESHES / GEOMETRIC_BAKE_FBXS。
上会话 round8 跑过 MIRROR_FIX=unified 实验（de4e085），shell 残留即可复现。

本探针对每个含 Pole/SwPole Model 的 FBX 输出一行指纹：
  <fbx_md5[:8]> | 配置串 | 每个相关 Model 的世界矩阵 3x3 列主序符号序列
跨进程跨 PYTHONHASHSEED 跑多轮，指纹全同 => 链路确定性实锤；
改环境变量后指纹变 => 「非确定性」实为配置漂移，悬案结案。

用法: python3 tools/probe_determinism.py [--all-models]
"""
import os, sys, hashlib
sys.path.insert(0, os.path.dirname(__file__))
from unity_yaml import UNITY_ROOT
from fbx_binary import parse as fbx_parse, p70
import extract_components as ec

WANT = ('SwPole', 'Pole', 'Switch Pole')


def fbx_files():
    out = []
    for root, _dirs, files in os.walk(os.path.join(UNITY_ROOT, 'Assets')):
        for fn in files:
            if fn.lower().endswith('.fbx'):
                out.append(os.path.join(root, fn))
    return sorted(out)


def main():
    cfg = '|'.join([
        f"MIRROR_FIX={os.environ.get('MIRROR_FIX', 's3gen')}",
        f"BAKE_FBX_M={os.environ.get('BAKE_FBX_M', '0')}",
        f"KEEP_PIN_MESHES={os.environ.get('KEEP_PIN_MESHES', '1')}",
        f"GEOM={os.environ.get('GEOMETRIC_BAKE_FBXS', '*')}",
        f"PYHASHSEED={os.environ.get('PYTHONHASHSEED', '<random>')}",
    ])
    # 定点复现悬案观测路径：Simple Switch.prefab 的 SwPole/Pole 节点
    # （prefab YAML -> scene_tree -> trs_matrix，即提取器真实构造链）
    import hashlib
    from unity_yaml import parse_prefab, scene_tree
    pf_path = os.path.join(UNITY_ROOT, 'Assets/Resources/Experiments/Basic Circuits/Simple Switch.prefab')
    pf = parse_prefab(pf_path)
    tree = scene_tree(pf)
    lines = []
    def walk(node, depth):
        nm = str(node['name'] or '')
        if 'pole' in nm.lower():
            t = node['transform']
            q = t['rotation']
            qx, qy, qz, qw = (q[i] for i in range(4)) if isinstance(q, (list, tuple)) \
                else (q['x'], q['y'], q['z'], q['w'])
            m = ec.trs_matrix(t, top_level=(depth == 1))
            sign = ''.join('0' if abs(m[i]) < 1e-9
                           else ('+' if m[i] > 0 else '-') for i in range(12))
            lines.append(f"{nm}: quat=({qx:+.4f},{qy:+.4f},{qz:+.4f},{qw:+.4f}) sign12={sign}")
        for ch in node.get('children', []):
            walk(ch, depth + 1)
    root = tree[0]
    for ch in root.get('children', []):
        walk(ch, 1)
    for fbx in ('Assets/Physics-Lab/Circuits/铡刀.FBX', 'Assets/Physics-Lab/Circuits/基础件.FBX'):
        d = open(os.path.join(UNITY_ROOT, fbx), 'rb').read()
        lines.append(f"{os.path.basename(fbx)} md5={hashlib.md5(d).hexdigest()[:10]}")
    print(f"SWITCH-PROBE {cfg}")
    for ln in lines:
        print(f"    {ln}")


if __name__ == '__main__':
    main()

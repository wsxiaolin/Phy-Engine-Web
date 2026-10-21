#!/usr/bin/env python3
"""Pin mesh A/B 裁决：官方预览 | A(KEEP_PIN=0) | B(KEEP_PIN=1) 三联图交 VLM。

问题背景：web 端接线柱此前由前端程序化生成（细圆柱），而 Unity FBX 内 Pin
节点带真实网格（官方预览里是大六角螺母香蕉插座）。矩阵双 bug 修复后保留
FBX pin 网格成为可能，本脚本裁决 A/B 哪个更接近官方真身。

用法: python3 tools/vlm_pin_ab.py
输入: build/pin_ab/compare_{Yes_Gate,Basic_Capacitor}.png
输出: build/pin_ab/vlm_{id}.json
"""
import os, sys, json, subprocess, time, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMP = os.path.join(ROOT, 'build', 'pin_ab')

PROMPT = """这是一张电路元件三联对比图：最左「OFFICIAL (Unity)」是 Unity 游戏内官方真实外观（唯一正确基准）；中间「A: KEEP_PIN=0」是 Web 复刻版方案 A 的渲染（接线柱由程序化生成的细圆柱替代，FBX 内 Pin 网格被剔除）；最右「B: KEEP_PIN=1」是方案 B 的渲染（保留了 FBX 内 Pin 节点真实网格）。请以最左官方预览为基准，逐项审查中间与右侧两版：
1. 接线柱/插座形态：官方的接线柱是什么形态（大小、粗细、颜色、结构）？A 和 B 哪一版的接线柱更接近官方？
2. 主体几何/比例：除接线柱外，主体（底座、核心部件）哪版更接近官方？
3. 有无可见缺陷：部件缺失、几何替换、比例失调、漂浮、穿模。
注意豁免：三图光照/影棚/相机不同，允许明暗与背景差异；程序化拾取球等小元素不算缺陷。
只输出严格 JSON，不要其他文字：
{"winner":"A 或 B 或 TIE","official_pin":"官方接线柱形态一句话","a_issues":["A 的问题"],"b_issues":["B 的问题"],"notes":"一句话总结"}"""

def call_vlm(img, out):
    for attempt in range(5):
        try:
            r = subprocess.run(['z-ai', 'vision', '-p', PROMPT, '-i', img, '-o', out],
                               capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                err = (r.stderr or '')[-300:]
                if '429' in err or 'Too many requests' in err:
                    wait = 30 * (attempt + 1)
                    print(f'  429 backing off {wait}s')
                    time.sleep(wait); continue
                raise RuntimeError(f'cli exit {r.returncode}: {err[-200:]}')
            data = json.load(open(out))
            content = data['choices'][0]['message']['content'].strip()
            m = re.search(r'\{.*\}', content, re.S)
            if not m: raise ValueError(f'no json: {content[:120]}')
            v = json.loads(m.group(0))
            if v.get('winner') not in ('A', 'B', 'TIE'): raise ValueError(f'bad: {v}')
            return v
        except Exception as e:
            if attempt == 4: return {'winner': 'ERROR', 'error': str(e)[:300]}
            time.sleep(5 * (attempt + 1))

for name in ['Yes_Gate', 'Basic_Capacitor']:
    img = os.path.join(CMP, f'compare_{name}.png')
    out = os.path.join(CMP, f'vlm_{name}.json')
    print(f'== {name}')
    v = call_vlm(img, out)
    print(json.dumps(v, ensure_ascii=False, indent=1))
    time.sleep(4)

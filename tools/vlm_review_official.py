#!/usr/bin/env python3
"""VLM 审校「Unity 官方预览 vs web 实况」对照图（build/compare_official/{id}.png）。

官方预览是游戏内真实外观（ground truth），webshot 是 web 端实况。
本脚本用于复核 compare_vlm（GLB refshot 基准）中判 FAIL 的元件：
refshot 是裸 GLB 影棚渲染（无程序化 pin 帽），webshot 含运行时引脚柱，
两者差异不等于产品缺陷——官方预览才能裁决。

用法: python3 tools/vlm_review_official.py [id1 id2 ...]   # 无参 = 全量
输出: build/compare_official_vlm/{id}.json + report.json
节流：每张间隔 GAP 秒（默认 4s）；429 退避 30/60/120s 重试。
"""
import os, sys, json, subprocess, time, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMP = os.path.join(ROOT, 'build', 'compare_official')
OUT = os.path.join(ROOT, 'build', 'compare_official_vlm')
GAP = int(os.environ.get('VLM_GAP', '4'))
os.makedirs(OUT, exist_ok=True)

PROMPT = """这是一张电路元件对照图。左半（蓝色标题条「Unity 官方预览 (in-game)」）是 Unity 游戏内的官方真实外观，作为唯一正确基准；右半（绿色标题条「web 场景实况」）是同一元件在 Web 复刻版中的实际渲染。请以左侧官方预览为基准，严格审查右侧 web 渲染是否忠实复刻：
1. 几何形状/主体结构是否与官方预览一致（部件构成、轮廓、立体感、比例）；
2. 主体配色与材质身份是否对应（左右光照/摄影机角度不同，允许明暗与背景差异，但各部件的颜色-功能对应应能识别）；
3. 有无可见缺陷：部件缺失、几何被替换成完全不同的形状、比例明显失调、穿模。
注意两点豁免（不算缺陷）：
a. 右图元件底部/周围可能出现红色或黑色小圆柱体（接线柱/引脚，顶部或带金属帽）——这是 web 端按 Unity 运行时 PinDefinition 程序化生成的功能件，官方预览图里因拍摄角度未必可见，属预期元素；元件由引脚柱支撑立于桌面是正确姿态，"悬空"结论仅在元件明显漂浮远离支撑面时成立。
b. 右图中的白色小字标签（电压/电流读数等）是正常 UI。
判定口径：只要右侧主体几何结构与官方预览一致、无部件缺失或错误替换、比例不失调，即判 PASS；引脚柱差异按豁免处理。只输出严格 JSON，不要输出任何其他文字：{"verdict":"PASS 或 FAIL","issues":["发现的问题，无则空数组"],"notes":"一句话对比结论"}"""

def call_vlm(img):
    # 临时文件放 /tmp：曾因写在 OUT 目录被误 commit（compare_official_vlm/_tmp.json）
    tmp = '/tmp/_vlm_review_official_tmp.json'
    for attempt in range(5):
        try:
            r = subprocess.run(['z-ai', 'vision', '-p', PROMPT, '-i', img, '-o', tmp],
                               capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                err = (r.stderr or '')[-300:]
                if ('429' in err or 'Too many requests' in err) and attempt < 4:
                    wait = 30 * (attempt + 1)
                    print(f'  429 rate-limited, backing off {wait}s ...')
                    time.sleep(wait)
                    continue
                raise RuntimeError(f'cli exit {r.returncode}: {err[-200:]}')
            data = json.load(open(tmp))
            content = data['choices'][0]['message']['content'].strip()
            m = re.search(r'\{.*\}', content, re.S)
            if not m:
                raise ValueError(f'no json in reply: {content[:120]}')
            verdict = json.loads(m.group(0))
            if verdict.get('verdict') not in ('PASS', 'FAIL'):
                raise ValueError(f'bad verdict: {verdict}')
            return verdict
        except Exception as e:
            if attempt == 4:
                return {'verdict': 'ERROR', 'issues': [str(e)[:300]], 'notes': ''}
            time.sleep(5 * (attempt + 1))

def main():
    args = sys.argv[1:]
    only = set(args)
    files = sorted(f for f in os.listdir(CMP)
                   if f.endswith('.png') and not f.startswith('grid_')
                   and (not only or f[:-4] in only))
    if not files:
        print('no official-pair images found in', CMP); sys.exit(1)
    report = {}
    for i, f in enumerate(files, 1):
        mid = f[:-4]
        img = os.path.join(CMP, f)
        t0 = time.time()
        v = call_vlm(img)
        report[mid] = v
        json.dump(v, open(os.path.join(OUT, f'{mid}.json'), 'w'), ensure_ascii=False, indent=1)
        print(f'[{i}/{len(files)}] {mid}: {v["verdict"]} ({time.time()-t0:.0f}s)'
              + (f' {"; ".join(v["issues"])[:150]}' if v.get("issues") else ''))
        if i < len(files):
            time.sleep(GAP)
    n_pass = sum(1 for v in report.values() if v['verdict'] == 'PASS')
    n_fail = sum(1 for v in report.values() if v['verdict'] == 'FAIL')
    n_err = sum(1 for v in report.values() if v['verdict'] == 'ERROR')
    summary = {'total': len(report), 'pass': n_pass, 'fail': n_fail, 'error': n_err, 'detail': report}
    json.dump(summary, open(os.path.join(OUT, 'report.json'), 'w'), ensure_ascii=False, indent=1)
    print(f'SUMMARY {n_pass} PASS / {n_fail} FAIL / {n_err} ERROR (total {len(report)})')
    if n_fail or n_err:
        sys.exit(2)

if __name__ == '__main__':
    main()

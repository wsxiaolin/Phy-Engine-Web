#!/usr/bin/env python3
"""VLM 逐张审校 Unity 源 vs web 对照拼图（build/compare/{id}.png）。

对每张对照图调用 z-ai vision（glm-5v-turbo）做严格一致性判定，
逐件输出 build/compare_vlm/{id}.json，并汇总 build/compare_vlm/report.json。
判定口径：几何结构一致 + 元件正常落桌 + 材质大体一致（允许光照环境差）+
无部件缺失/朝向错误/比例失调/标签遮挡 → PASS。

用法: python3 tools/vlm_review_pairs.py [id1 id2 ...]   # 无参 = 全量 compare/
      python3 tools/vlm_review_pairs.py --retry-error  # 只补 ERROR/缺失，跳过已判 PASS/FAIL
节流：每张间隔 GAP 秒（默认 4s）；429 限流时长退避 30/60/120s 后重试。
"""
import os, sys, json, subprocess, time, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMP = os.path.join(ROOT, 'build', 'compare')
OUT = os.path.join(ROOT, 'build', 'compare_vlm')
GAP = int(os.environ.get('VLM_GAP', '4'))
os.makedirs(OUT, exist_ok=True)

PROMPT = """这是一张电路元件渲染对照图。左半（蓝色标题条「Unity 源数据」）是元件 GLB 在中性影棚中的渲染参照；右半（绿色标题条「web 场景实况」）是同一元件在 Web 应用场景内的实际渲染。请严格对比左右两侧，逐项检查：
1. 几何形状/主体结构是否一致（部件构成、轮廓、比例）；
2. 右图中元件是否正常放置在桌面上（不得悬空、不得明显陷入桌面）；
3. 材质与颜色是否大体一致（左右光照环境不同，允许整体明暗/色调差异，但部件配色身份应能对应）；
4. 有无可见缺陷：部件缺失、朝向/旋转错误、比例明显失调、标签文字遮挡主体、模型穿模。
注意：右图可能出现白色小字标签（如电压/电流读数），这是正常的 UI 元素，不算缺陷；右图背景为房间场景、左图为灰色影棚，背景差异不算缺陷。
右图元件上/底部可能出现红色或黑色的小圆柱体（接线柱/引脚柱，顶部带金属帽），这是 web 端按 Unity ChipComponent 运行时约定程序化生成的功能件（左图 GLB 参照里被剔除），属于预期元素，不算多余几何、不算悬空缺陷——元件由接线柱支撑立于桌面是正确姿态；也不要把接线柱计入"部件配色不一致"。只输出严格 JSON，不要输出任何其他文字：{"verdict":"PASS 或 FAIL","issues":["发现的问题，无则空数组"],"notes":"一句话对比结论"}"""

def call_vlm(img):
    tmp = os.path.join(OUT, '_tmp.json')
    for attempt in range(5):
        try:
            r = subprocess.run(['z-ai', 'vision', '-p', PROMPT, '-i', img, '-o', tmp],
                               capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                err = (r.stderr or '')[-300:]
                if '429' in err or 'Too many requests' in err:
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
    retry_error = '--retry-error' in args
    only = set(a for a in args if not a.startswith('--'))
    files = sorted(f for f in os.listdir(CMP)
                   if f.endswith('.png') and not f.startswith('grid_')
                   and (not only or f[:-4] in only))
    if not files:
        print('no pair images found in', CMP); sys.exit(1)
    report = {}
    # 载入已有判定（--retry-error 模式下 PASS/FAIL 保留，只补 ERROR/缺失）
    for f in files:
        mid = f[:-4]
        cached = os.path.join(OUT, f'{mid}.json')
        if retry_error and os.path.exists(cached):
            try:
                v = json.load(open(cached))
                if v.get('verdict') in ('PASS', 'FAIL'):
                    report[mid] = v
            except Exception:
                pass
    skipped = len(report)
    if skipped:
        print(f'reusing {skipped} cached PASS/FAIL verdicts')
    for i, f in enumerate(files, 1):
        mid = f[:-4]
        if mid in report:
            print(f'[{i}/{len(files)}] {mid}: cached {report[mid]["verdict"]}')
            continue
        img = os.path.join(CMP, f)
        t0 = time.time()
        v = call_vlm(img)
        report[mid] = v
        json.dump(v, open(os.path.join(OUT, f'{mid}.json'), 'w'), ensure_ascii=False, indent=1)
        print(f'[{i}/{len(files)}] {mid}: {v["verdict"]} ({time.time()-t0:.0f}s)'
              + (f' {"; ".join(v["issues"])[:150]}' if v.get('issues') else ''))
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

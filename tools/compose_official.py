#!/usr/bin/env python3
"""Compose official-Unity-preview vs web-shot side-by-side images.
official: unity/Assets/Physics-Lab/Previews/Circuits/{id-with-dashes}.png
web:      build/webshot/{id}.png
out:      build/compare_official/{id}.png  (+ grid sheets)
The official preview is the real in-game look (ground truth)."""
import os, sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNI = os.path.join(ROOT, 'unity', 'Assets', 'Physics-Lab', 'Previews', 'Circuits')
WEB = os.path.join(ROOT, 'build', 'webshot')
OUT = os.path.join(ROOT, 'build', 'compare_official')
BG = (224, 227, 232)
os.makedirs(OUT, exist_ok=True)

SUPPORTED = ["Ground Component", "Resistor", "Basic Capacitor", "Basic Inductor", "Battery Source", "Simple Switch", "Push Switch", "Air Switch", "Transformer", "Mutual Inductor", "Rectifier", "Logic Input", "Logic Output", "Or Gate", "And Gate", "Nand Gate", "Nor Gate", "Xor Gate", "Xnor Gate", "Imp Gate", "Nimp Gate", "Yes Gate", "No Gate", "Schmitt Trigger", "Comparator", "JK Flipflop", "T Flipflop", "Real-T Flipflop", "Multiplier", "D Flipflop", "Half Adder", "Full Adder", "Half Subtractor", "Full Subtractor", "Counter", "Random Generator"]

def font(sz):
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
              '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
              '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc'):
        if os.path.exists(p):
            try: return ImageFont.truetype(p, sz)
            except Exception: pass
    return ImageFont.load_default()

def flatten(img):
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGBA')
        base = Image.new('RGB', img.size, BG)
        base.paste(img, mask=img.split()[3])
        return base
    return img.convert('RGB')

def uni_path(mid):
    # official preview naming is inconsistent: spaces / dashes / different names
    ALIAS = {
        'Ground Component': 'Ground',
        'Basic Capacitor': 'Capacitor',
        'Basic Inductor': 'Inductor',
        # 芯片家族（Schmitt/Comparator/各 Flipflop/Adder/Subtractor/Counter/
        # Random Generator/Multiplier）在 Unity 共享同一 Chip prefab + 运行时
        # 丝印，官方预览只有一张 Chip.png——全家族以 Chip.png 为对照代理
        # （GLB 侧已验证：12 件 md5 一致，Schmitt_Trigger 仅丝印 296B 差异）
        'D Flipflop': 'Chip', 'JK Flipflop': 'Chip', 'T Flipflop': 'Chip',
        'Real-T Flipflop': 'Chip', 'Schmitt Trigger': 'Chip', 'Comparator': 'Chip',
        'Multiplier': 'Chip', 'Half Adder': 'Chip', 'Full Adder': 'Chip',
        'Half Subtractor': 'Chip', 'Full Subtractor': 'Chip', 'Counter': 'Chip',
        'Random Generator': 'Chip',
    }
    name = ALIAS.get(mid, mid)
    for cand in (name, name.replace(' ', '-'), name.replace('-', ' ')):
        p = os.path.join(UNI, cand + '.png')
        if os.path.exists(p):
            return p
    return os.path.join(UNI, name.replace(' ', '-') + '.png')

def pair(mid):
    up, wp = uni_path(mid), os.path.join(WEB, mid.replace(' ', '_') + '.png')
    if not (os.path.exists(up) and os.path.exists(wp)):
        return None
    u, w = flatten(Image.open(up)), flatten(Image.open(wp))
    H = 520
    u = u.resize((int(u.width * H / u.height), H))
    w = w.resize((int(w.width * H / w.height), H))
    GAP, BAR, BOT = 10, 34, 30
    canvas = Image.new('RGB', (u.width + w.width + GAP, H + BAR + BOT), (250, 250, 250))
    canvas.paste(u, (0, BAR)); canvas.paste(w, (u.width + GAP, BAR))
    d = ImageDraw.Draw(canvas)
    f1, f2 = font(20), font(18)
    d.rectangle([0, 0, u.width - 1, BAR - 2], fill=(70, 90, 130))
    d.rectangle([u.width + GAP, 0, canvas.width - 1, BAR - 2], fill=(50, 120, 80))
    d.text((8, 6), 'Unity 官方预览 (in-game)', font=f1, fill=(255, 255, 255))
    d.text((u.width + GAP + 8, 6), 'web 场景实况', font=f1, fill=(255, 255, 255))
    d.text((8, BAR + H + 6), mid, font=f2, fill=(40, 40, 40))
    canvas.save(os.path.join(OUT, mid.replace(' ', '_') + '.png'))
    return canvas

def sheet(canvases, g):
    cw = max(c.width for c in canvases)
    ch = max(c.height for c in canvases)
    cols, rows = 2, 3
    sc = Image.new('RGB', (cols * cw + 12, rows * ch + 12), (30, 30, 34))
    for i, c in enumerate(canvases):
        sc.paste(c, (6 + (i % cols) * (cw + 2), 6 + (i // cols) * (ch + 2)))
    sc = sc.resize((sc.width // 2, sc.height // 2))
    sc.save(os.path.join(OUT, f'grid_{g}.png'))

def main():
    only = sys.argv[1:]
    ids = only or SUPPORTED
    sheets, buf = [], []
    for g, start in enumerate(range(0, len(ids), 6)):
        for mid in ids[start:start + 6]:
            c = pair(mid)
            if c is None:
                print('MISS', mid)
                continue
            buf.append(c)
        if buf:
            sheet(buf, g); sheets.append(g)
        buf = []
    print(f'sheets={len(sheets)} → {OUT}')

if __name__ == '__main__':
    main()

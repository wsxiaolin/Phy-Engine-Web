// 批量元件截图：36 个 supported 元件，每屏 6 个（2×3），输出 build/grid_N.png
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { join, extname } from "node:path";
const ROOT = join(process.cwd(), "dist");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".glb": "model/gltf-binary", ".wasm": "application/wasm" };
const srv = createServer((req, res) => {
  let p = req.url.split("?")[0]; if (p === "/") p = "/index.html";
  const f = join(ROOT, p);
  if (!existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": MIME[extname(f)] || "application/octet-stream" });
  res.end(readFileSync(f));
});
await new Promise((r) => srv.listen(8951, r));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://localhost:8951/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
const SUPPORTED = new Set(["Ground Component", "Resistor", "Basic Capacitor", "Basic Inductor", "Battery Source", "Simple Switch", "Push Switch", "Air Switch", "Transformer", "Mutual Inductor", "Rectifier", "Logic Input", "Logic Output", "Or Gate", "And Gate", "Nand Gate", "Nor Gate", "Xor Gate", "Xnor Gate", "Imp Gate", "Nimp Gate", "Yes Gate", "No Gate", "Schmitt Trigger", "Comparator", "JK Flipflop", "T Flipflop", "Real-T Flipflop", "Multiplier", "D Flipflop", "Half Adder", "Full Adder", "Half Subtractor", "Full Subtractor", "Counter", "Random Generator"]);
const catJson = JSON.parse(readFileSync(join(process.cwd(), "../build/assets/catalog.json"), "utf8"));
const items = catJson.items || catJson;
const names = items.filter((i) => SUPPORTED.has(i.ModelID)).map((i) => ({ id: i.ModelID, label: i.FriendlyName || i.ModelID }));
console.log("batch:", names.length, JSON.stringify(names));
for (let g = 0; g * 6 < names.length; g++) {
  const group = names.slice(g * 6, g * 6 + 6);
  await page.evaluate(async (group) => {
    const app = window.__app;
    app.reset();
    const els = [];
    for (let i = 0; i < group.length; i++) {
      const e = app.experiment.addElement({ modelId: group[i].id, label: group[i].label, position: { x: 0, y: 0.78, z: 0 }, properties: {} });
      els.push(e);
    }
    await Promise.all(els.map((e) => app.instantiate(e)));
    // ---- 尺寸自适应布局：行贪心装填（间距按元件 GLB bbox 实测，兼容 0.64m 级大底板）----
    const MARGIN = 0.06, MAXW = 1.38, MAXD = 1.28; // 桌面半宽 0.78/半深 0.72 → 全域 1.56×1.44 内留边
    const entries = els.map((e) => {
      const g = app.elementObjects.get(e.id);
      const s = g?.userData.size || { x: 0.12, y: 0.05, z: 0.12 };
      return { e, g, w: (s.x || 0.12) + MARGIN, d: (s.z || 0.12) + MARGIN };
    });
    entries.sort((a, b) => Math.max(b.w, b.d) - Math.max(a.w, a.d));
    const rows = [];
    for (const it of entries) {
      let row = rows[rows.length - 1];
      const rowW = row ? row.reduce((s, r) => s + r.w, 0) - MARGIN : 0;
      if (!row || rowW + it.w > MAXW) { row = []; rows.push(row); }
      row.push(it);
    }
    let rowDepths = rows.map((r) => Math.max(...r.map((it) => it.d)));
    let totalD = rowDepths.reduce((a, b) => a + b, 0) + MARGIN * (rows.length - 1);
    if (totalD > MAXD && rows.length > 1) { MARGIN_SQUEEZE: { // 超深则压缩行距（允许大件贴近，仍不重叠：MARGIN≥0.02）
      const m2 = Math.max(0.02, MARGIN - (totalD - MAXD) / (rows.length - 1));
      rowDepths = rows.map((r) => Math.max(...r.map((it) => it.d - (MARGIN - m2))));
      totalD = rowDepths.reduce((a, b) => a + b, 0) + m2 * (rows.length - 1);
    } }
    let z = -totalD / 2;
    rows.forEach((row, ri) => {
      const rowW = row.reduce((s, it) => s + it.w, 0) - MARGIN;
      let x = -rowW / 2;
      row.forEach((it) => {
        const px = x + it.w / 2, pz = z + rowDepths[ri] / 2;
        it.g.position.set(px, 0.78, pz);
        it.e.position = { x: px, y: 0.78, z: pz };
        x += it.w;
      });
      z += rowDepths[ri] + MARGIN;
    });
    // ---- 相机自动取景：俯角 70°，覆盖布局宽深 ----
    const cam = app.world.camera, c = app.world.controls;
    const layW = Math.max(...rows.map((row, ri) => row.reduce((s, it) => s + it.w, 0) - MARGIN));
    const layD = totalD;
    const fovY = (cam.fov * Math.PI) / 180;
    const fovX = 2 * Math.atan(Math.tan(fovY / 2) * cam.aspect);
    const need = Math.max((layW / 2) / Math.tan(fovX / 2), (layD / 2) / Math.tan(fovY / 2)) * 1.18;
    const tilt = (70 * Math.PI) / 180;
    cam.position.set(0, 0.78 + need * Math.sin(tilt), need * Math.cos(tilt));
    c.target.set(0, 0.78, 0);
    c.update();
  }, group);
  await page.waitForTimeout(600);
  await page.screenshot({ path: `../build/grid_${g}.png` });
  console.log("shot", g, group.map((x) => x.label).join(","));
}
console.log("PAGEERRORS:", errors.length, errors[0] || "");
await browser.close();
srv.close();

// 端到端验证：元件落桌 + 导线端点是否落在接线柱上 + 仿真数值
// 跑法：node tools/verify_scene.mjs（内起 http 服务 + playwright）
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { join, extname } from "node:path";

const ROOT = join(process.cwd(), "web/dist");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".glb": "model/gltf-binary", ".wasm": "application/wasm", ".png": "image/png" };
const srv = createServer((req, res) => {
  let p = req.url.split("?")[0];
  if (p === "/") p = "/index.html";
  const f = join(ROOT, p);
  if (!existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": MIME[extname(f)] || "application/octet-stream" });
  res.end(readFileSync(f));
});
await new Promise((r) => srv.listen(8931, r));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));
page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE:", m.text().slice(0, 200)); });
await page.goto("http://localhost:8931/");
await page.waitForFunction(() => window.__app && window.__app.experiment, null, { timeout: 30000 });
await page.waitForTimeout(2500); // 首屏 GLB

// 布一个典型实验：电池、电阻、电流表（3 pin 视觉检验）、与门（芯片 pin 公式检验）
const setup = await page.evaluate(async () => {
  const app = window.__app;
  app.reset();
  const mk = async (modelId, x, z, rotY = 0, props = {}) => {
    const el = app.experiment.addElement({ modelId, label: modelId, position: { x, y: 0.78, z }, rotY, properties: props });
    await app.instantiate(el);
    return el;
  };
  const bat = await mk("Battery Source", -0.3, 0, 0, { 电压: 3 });
  const res = await mk("Resistor", 0.15, 0.25, 0, { 电阻: 100 });
  const gal = await mk("Galvanometer", 0.35, -0.15);
  const andg = await mk("And Gate", -0.25, -0.3);
  // 仿真回路：电池+ → 电阻，电阻 → 电池-（电流表不被引擎支持，纯视觉）
  app.experiment.addWire(bat.id, 1, res.id, 0, "红色导线");
  app.experiment.addWire(res.id, 1, bat.id, 0, "黑色导线");
  // 视觉支路：电流表串进电路外观（不影响引擎 payload，会被过滤）
  app.experiment.addWire(bat.id, 0, gal.id, 0, "黑色导线");
  app.experiment.addWire(gal.id, 1, res.id, 1, "黑色导线");
  app.syncWires();
  app.simulate(false);
  await new Promise((r) => setTimeout(r, 600));
  // 采集数值证据
  const stats = app.experiment.elements.map((e) => ({ id: e.label, stat: e.statistics }));
  return { stats };
});
console.log("STATS:", JSON.stringify(setup.stats, null, 1).slice(0, 500));

// 数值断言：电池 3V 默认? DEFAULT_PROPS 电池=3 → 电流 = 3/100 = 0.03
const s = Object.fromEntries(setup.stats.map((x) => [x.id, x.stat]));
const ok = s["Battery Source"] && Math.abs((s["Battery Source"].电压 || 0) - 3) < 1e-6
  && Math.abs(Math.abs(s["Battery Source"].电流) - 0.03) < 1e-3
  && s["Resistor"] && Math.abs(s["Resistor"].电流 - (-s["Battery Source"].电流)) < 1e-3;
console.log("NUMERIC CHECK:", ok ? "PASS" : "FAIL", JSON.stringify(s));

await page.screenshot({ path: "build/verify_view.png" });

// 特写：俯视桌面，看导线端点是否压在接线柱上
await page.evaluate(() => {
  const app = window.__app;
  const cam = app.world.camera;
  const c = app.world.controls;
  cam.position.set(0.05, 1.75, 0.55);
  c.target.set(0.05, 0.78, 0.0);
  c.update();
});
await page.waitForTimeout(600);
await page.screenshot({ path: "build/verify_top.png" });
console.log("screenshots saved");
await browser.close();
srv.close();

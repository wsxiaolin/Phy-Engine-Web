// M8 电表专项 e2e：灵敏电流计串入主回路，读数/刻度/指针角三重断言。
// 跑法：node tools/verify_meter.mjs（内起 http 服务 + playwright，加载 web/dist）
// 场景：电池 3V → 1MΩ 电阻 → 灵敏电流计 Pin2(正) → Pin1(负) → 电池-
// 期望：i = 3µA；刻度 = -i/3e-6 → |1|（满偏，烧毁阈值 ±1.05 之内）；
//       指针 eulerY = lerp(46°, -46°, t)，|刻度|=1 → t=0 或 1 → ±46° 全偏转。
// 数值与 Unity Meters/Galvanometer.cs 一比一（R=100，量程 3e-6，Break ±1.05）。
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
await new Promise((r) => srv.listen(8933, r));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("pageerror", (e) => { console.log("PAGEERROR:", e.message); process.exitCode = 1; });
page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE:", m.text().slice(0, 200)); });
await page.goto("http://localhost:8933/");
await page.waitForFunction(() => window.__app && window.__app.experiment, null, { timeout: 30000 });
await page.waitForTimeout(2500); // 首屏 GLB

const setup = await page.evaluate(async () => {
  const app = window.__app;
  app.reset();
  const mk = async (modelId, x, z, props = {}) => {
    const el = app.experiment.addElement({ modelId, label: modelId, position: { x, y: 0.78, z }, rotY: 0, properties: props });
    await app.instantiate(el);
    return el;
  };
  const bat = await mk("Battery Source", -0.35, 0, { 电压: 3 });
  const res = await mk("Resistor", 0.0, 0.2, { 电阻: 1e6 }); // 3V/1MΩ = 3µA 满偏
  const gal = await mk("Galvanometer", 0.35, -0.05);
  app.experiment.addWire(bat.id, 1, res.id, 0, "红色导线");
  app.experiment.addWire(res.id, 1, gal.id, 1, "黑色导线");
  app.experiment.addWire(gal.id, 0, bat.id, 0, "黑色导线");
  app.syncWires();
  app.simulate(false);
  await new Promise((r) => setTimeout(r, 600));
  return app.experiment.elements.map((e) => ({ id: e.label, stat: e.statistics, broken: !!e.broken }));
});

const s = Object.fromEntries(setup.map((x) => [x.id, x]));
const gal = s["Galvanometer"] || { stat: {} };
const gs = gal.stat || {};
const okNum =
  Math.abs((s["Battery Source"]?.stat?.电压 || 0) - 3) < 1e-6
  && Math.abs(Math.abs(s["Battery Source"]?.stat?.电流 || 0) - 3e-6) < 1e-7
  && Math.abs(Math.abs(gal.电流 ?? gs.电流 ?? 0) - 3e-6) < 1e-7
  && gs.刻度 !== undefined && Math.abs(Math.abs(gs.刻度) - 1) < 0.02
  && !gs.烧毁 && !gal.broken;
console.log("METER NUMERIC:", okNum ? "PASS" : "FAIL", JSON.stringify(setup));
if (!okNum) process.exitCode = 1;

// 指针角断言（Unity RenderPointer lerp(46,-46)）：|刻度|=1 → t=0/1 → ±46°。
// 零位（未连接/刻度 0）为 23°，只要 ≠23° 且达 ±46° 即驱动链全通。
const needle = await page.evaluate(() => {
  const app = window.__app;
  for (const [id, g] of app.elementObjects) {
    const el = app.experiment.getElement(id);
    if (el && el.modelId === "Galvanometer") {
      const n = g.userData.meterNeedle;
      return n ? { found: true, deg: +(n.rotation.y * 180 / Math.PI).toFixed(1) } : { found: false };
    }
  }
  return { found: false };
});
const okNeedle = needle.found && Math.abs(Math.abs(needle.deg) - 46) < 2;
console.log("NEEDLE:", okNeedle ? "PASS" : "FAIL", JSON.stringify(needle));
if (!okNeedle) process.exitCode = 1;

// 俯视特写截图（指针 + 表盘 + 标签读数同框）
await page.evaluate(() => {
  const app = window.__app;
  app.world.camera.position.set(0.0, 1.55, 0.5);
  app.world.controls.target.set(0.0, 0.78, 0.05);
  app.world.controls.update();
});
await page.waitForTimeout(700);
await page.screenshot({ path: "build/verify_meter_deflect.png" });
await browser.close();
srv.close();
console.log("METER E2E", process.exitCode ? "FAILED" : "DONE");

// LED 指示灯状态截图：Logic Input OFF/ON + Logic Output 红灯（联动电路）
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
await new Promise((r) => srv.listen(8936, r));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto("http://localhost:8936/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);

const mk = async (app, m, x, z, props) => {
  const e = app.experiment.addElement({ modelId: m, label: m, position: { x, y: 0.78, z }, properties: props });
  await app.instantiate(e);
  return e;
};
const cam = (app, x, y, z, tx, ty, tz) => {
  const c = app.world.controls;
  app.world.camera.position.set(x, y, z);
  c.target.set(tx, ty, tz); c.update();
};

// 场景1: Logic Input OFF（开关=0，绿灯灭，按钮-关）
await page.evaluate(async () => {
  const app = window.__app;
  app.reset();
  const el = await app.addPart("Logic Input", 0, 0, { 开关: 0 });
  window.__el = el;
  const c = app.world.controls;
  app.world.camera.position.set(0, 0.95, 0.4); c.target.set(0, 0.8, 0); c.update();
});
await page.waitForTimeout(900);
await page.screenshot({ path: "../build/led_input_off.png" });

// 场景2: 同一元件 开关=1（绿灯亮+自发光+光晕，按钮-开）
await page.evaluate(async () => {
  const app = window.__app;
  const el = window.__el;
  el.properties["开关"] = 1;
  app.syncLED(el);
  app.scheduleSimulate();
});
await page.waitForTimeout(900);
await page.screenshot({ path: "../build/led_input_on.png" });

// 场景3: Logic Input(开) --wire--> Logic Output（输出 H → 红灯亮）
await page.evaluate(async () => {
  const app = window.__app;
  app.reset();
  const li = await app.addPart("Logic Input", -0.22, 0, { 开关: 1 });
  const lo = await app.addPart("Logic Output", 0.22, 0, {});
  app.experiment.addWire(li.id, 0, lo.id, 0, "绿色导线");
  app.syncWires();
  app.scheduleSimulate();
  const c = app.world.controls;
  app.world.camera.position.set(0, 0.95, 0.55); c.target.set(0, 0.8, 0); c.update();
});
await page.waitForTimeout(1400);
const stats = await page.evaluate(() => {
  const app = window.__app;
  return app.experiment.elements.map((e) => ({ m: e.modelId, st: e.statistics }));
});
console.log("stats:", JSON.stringify(stats));
await page.screenshot({ path: "../build/led_output_on.png" });

await browser.close();
srv.close();
console.log("DONE");

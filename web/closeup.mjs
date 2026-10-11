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
await new Promise((r) => srv.listen(8933, r));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto("http://localhost:8933/", { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
await page.evaluate(async () => {
  const app = window.__app;
  app.reset();
  const el = app.experiment.addElement({ modelId: "Galvanometer", label: "G", position: { x: 0, y: 0.78, z: 0 }, rotY: 0, properties: {} });
  await app.instantiate(el);
  const g = app.elementObjects.get(el.id);
  import("./src/components.js").then((m) => m.setPinsVisible(g, true));
  const cam = app.world.camera, c = app.world.controls;
  cam.position.set(0, 0.95, 0.55); c.target.set(0, 0.82, 0.06); c.update();
});
await page.waitForTimeout(800);
await page.screenshot({ path: "../build/galv_closeup.png" });
// 电池+电阻特写
await page.evaluate(async () => {
  const app = window.__app;
  app.reset();
  const mk = async (m, x, z, props) => { const e = app.experiment.addElement({ modelId: m, label: m, position: { x, y: 0.78, z }, properties: props }); await app.instantiate(e); return e; };
  const bat = await mk("Battery Source", 0, 0, { 电压: 3 });
  const res = await mk("Resistor", 0.25, 0, { 电阻: 100 });
  app.experiment.addWire(bat.id, 1, res.id, 0, "红色导线");
  app.experiment.addWire(res.id, 1, bat.id, 0, "黑色导线");
  app.syncWires();
  const cam = app.world.camera, c = app.world.controls;
  cam.position.set(0.12, 1.35, 0.85); c.target.set(0.12, 0.78, 0); c.update();
});
await page.waitForTimeout(800);
await page.screenshot({ path: "../build/batres_closeup.png" });
console.log("done");
await browser.close(); srv.close();

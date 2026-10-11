import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { join, extname } from "node:path";
const ROOT = join(process.cwd(), "web/dist");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".glb": "model/gltf-binary", ".wasm": "application/wasm" };
const srv = createServer((req, res) => {
  let p = req.url.split("?")[0]; if (p === "/") p = "/index.html";
  const f = join(ROOT, p);
  if (!existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": MIME[extname(f)] || "application/octet-stream" });
  res.end(readFileSync(f));
});
await new Promise((r) => srv.listen(8932, r));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));
await page.goto("http://localhost:8932/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
const diag = await page.evaluate(async () => {
  const app = window.__app;
  app.reset();
  const mk = async (modelId, x, z, rotY = 0, props = {}) => {
    const el = app.experiment.addElement({ modelId, label: modelId, position: { x, y: 0.78, z }, rotY, properties: props });
    await app.instantiate(el);
    return el;
  };
  const bat = await mk("Battery Source", -0.3, 0, 0, { 电压: 3 });
  const res = await mk("Resistor", 0.15, 0.25, 0, { 电阻: 100 });
  const out = [];
  for (const el of app.experiment.elements) {
    const g = app.elementObjects.get(el.id);
    if (!g) { out.push({ id: el.label, err: "no object" }); continue; }
    const box = new (g.children[0].constructor.prototype.constructor === Object ? Object : Object)();
    // 用 three 的 Box3
    const h = app._selectBox; h.setFromObject(g); h.geometry.computeBoundingBox(); const b = h.geometry.boundingBox;
    out.push({
      id: el.label, pos: { ...el.position }, rotY: el.rotY,
      size: { x: +(b.max.x - b.min.x).toFixed(3), y: +(b.max.y - b.min.y).toFixed(3), z: +(b.max.z - b.min.z).toFixed(3) },
      min: { x: +b.min.x.toFixed(3), y: +b.min.y.toFixed(3), z: +b.min.z.toFixed(3) },
      pins: (g.userData.pinLocal || []).map((p) => ({ n: g.userData.pinNames, w: null })) && (g.userData.pinLocal || []).map((p, i) => {
        const w = g.localToWorld(p.clone());
        return { i, x: +w.x.toFixed(3), y: +w.y.toFixed(3), z: +w.z.toFixed(3) };
      }),
    });
  }
  return out;
});
console.log(JSON.stringify(diag, null, 1));
await browser.close(); srv.close();

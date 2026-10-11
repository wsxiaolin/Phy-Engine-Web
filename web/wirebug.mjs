import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { join, extname } from "node:path";
const ROOT = join(process.cwd(), "dist");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".glb": "model/gltf-binary", ".wasm": "application/wasm" };
const srv = createServer((req, res) => {
  let p = req.url.split("?")[0]; if (p === "/") p = "/index.html";
  const f = join(ROOT, p);
  if (!existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": MIME[extname(f)] || "application/octet-stream" });
  res.end(readFileSync(f));
});
await new Promise((r) => srv.listen(8935, r));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto("http://localhost:8935/", { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
const out = await page.evaluate(async () => {
  const app = window.__app;
  app.reset();
  const mk = async (m, x, z, props) => { const e = app.experiment.addElement({ modelId: m, label: m, position: { x, y: 0.78, z }, properties: props }); await app.instantiate(e); return e; };
  const bat = await mk("Battery Source", 0, 0, { 电压: 3 });
  const res = await mk("Resistor", 0.25, 0, { 电阻: 100 });
  app.experiment.addWire(bat.id, 1, res.id, 0, "红色导线");
  app.experiment.addWire(res.id, 1, bat.id, 0, "黑色导线");
  app.syncWires();
  await new Promise((r) => setTimeout(r, 300));
  const wires = [];
  app.wireSystem.group.traverse((o) => {
    if (o.isMesh) {
      o.geometry.computeBoundingBox();
      const bb = o.geometry.boundingBox;
      wires.push({
        color: "#" + o.material.color.getHexString(),
        bb: { x: [+bb.min.x.toFixed(3), +bb.max.x.toFixed(3)], y: [+bb.min.y.toFixed(3), +bb.max.y.toFixed(3)], z: [+bb.min.z.toFixed(3), +bb.max.z.toFixed(3)] },
        verts: o.geometry.attributes.position.count,
        radial: o.geometry.parameters?.radialSegments, tubular: o.geometry.parameters?.tubularSegments,
        radius: o.geometry.parameters?.radius,
      });
    }
  });
  return wires;
});
console.log(JSON.stringify(out, null, 1));
await browser.close(); srv.close();

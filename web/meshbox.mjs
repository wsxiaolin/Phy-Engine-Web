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
await new Promise((r) => srv.listen(8934, r));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto("http://localhost:8934/", { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
const out = await page.evaluate(async () => {
  const app = window.__app;
  const el = app.experiment.addElement({ modelId: "Battery Source", label: "B", position: { x: 0, y: 0.78, z: 0 }, properties: { 电压: 3 } });
  await app.instantiate(el);
  const g = app.elementObjects.get(el.id);
  // 借 app 的 three：用 selectionBox helper 不行，直接算：遍历 mesh 用 setFromObject
  const res = [];
  g.traverse((o) => {
    if (o.isMesh) {
      o.geometry.computeBoundingBox();
      const bb = o.geometry.boundingBox.clone();
      // 8 角点变换到世界
      let minx=1e9,miny=1e9,minz=1e9,maxx=-1e9,maxy=-1e9,maxz=-1e9;
      const pos = o.geometry.attributes.position;
      const step = Math.max(1, Math.floor(pos.count / 400));
      for (let i = 0; i < pos.count; i += step) {
        const v = o.localToWorld(new (o.position.constructor)(pos.getX(i), pos.getY(i), pos.getZ(i)));
        minx=Math.min(minx,v.x);maxx=Math.max(maxx,v.x);
        miny=Math.min(miny,v.y);maxy=Math.max(maxy,v.y);
        minz=Math.min(minz,v.z);maxz=Math.max(maxz,v.z);
      }
      res.push({ name: o.name || o.parent?.name || "?", box: { x: [+minx.toFixed(3), +maxx.toFixed(3)], y: [+miny.toFixed(3), +maxy.toFixed(3)], z: [+minz.toFixed(3), +maxz.toFixed(3)] } });
    }
  });
  return res;
});
console.log(JSON.stringify(out, null, 1));
await browser.close(); srv.close();

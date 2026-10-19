// probe_world.mjs — 世界坐标包围盒探针：逐元件 dump 世界 bbox、根变换、与桌面 0.78 的间隙
// 用法: node probe_world.mjs "Basic Capacitor" "Air Switch" ...
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { join, extname } from "node:path";

const ROOT = join(process.cwd(), "dist");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".glb": "model/gltf-binary", ".wasm": "application/wasm" };
const srv = createServer((req, res) => {
  let p = req.url.split("?")[0]; if (p === "/") p = "/index.html";
  const f = join(ROOT, p);
  res.writeHead(200, { "Content-Type": MIME[extname(f)] || "application/octet-stream" });
  res.end(readFileSync(f));
});
await new Promise((r) => srv.listen(8957, r));

const ids = process.argv.slice(2);
if (!ids.length) { console.log("no ids"); process.exit(1); }
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 720, height: 720 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://localhost:8957/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);

const helper = `
window.__wbox = (g) => {
  g.updateWorldMatrix(true, true);
  const mn = [1e9,1e9,1e9], mx = [-1e9,-1e9,-1e9];
  g.traverse((o) => {
    if (!o.isMesh || !o.geometry) return;
    if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
    const bb = o.geometry.boundingBox, e = o.matrixWorld.elements;
    for (let xi=0; xi<2; xi++) for (let yi=0; yi<2; yi++) for (let zi=0; zi<2; zi++) {
      const px = xi?bb.max.x:bb.min.x, py = yi?bb.max.y:bb.min.y, pz = zi?bb.max.z:bb.min.z;
      for (let i=0;i<3;i++) {
        const v = e[i]*px + e[4+i]*py + e[8+i]*pz + e[12+i];
        if (v<mn[i]) mn[i]=v; if (v>mx[i]) mx[i]=v;
      }
    }
  });
  return { min: mn.map(v=>Math.round(v*1000)/1000), max: mx.map(v=>Math.round(v*1000)/1000) };
};
`;
await page.evaluate(helper);

const TABLE_Y = 0.78;
for (const mid of ids) {
  const r = await page.evaluate(async (modelId) => {
    const app = window.__app;
    app.reset();
    const e = app.experiment.addElement({ modelId, label: "", position: { x: 0, y: 0.78, z: 0 }, properties: {} });
    await app.instantiate(e);
    const g = app.elementObjects.get(e.id);
    const bb = window.__wbox(g);
    const rs = g.rotation ? [g.rotation.x, g.rotation.y, g.rotation.z] : null;
    // 子节点里的 pin 组世界位置（pins 是程序化生成组）
    const pins = [];
    g.traverse((o) => { if (o.name === "pins") { const e = o.matrixWorld.elements; pins.push([+e[12].toFixed(3), +e[13].toFixed(3), +e[14].toFixed(3)]); } });
    return { bb, scale: g.scale.toArray().map(v=>+v.toFixed(4)), rotation: rs?.map(v=>+v.toFixed(3)), position: g.position.toArray().map(v=>+v.toFixed(3)), pins };
  }, mid).catch((err) => ({ err: String(err) }));
  if (r.err) { console.log(`## ${mid}: ERROR ${r.err.slice(0,150)}`); continue; }
  const [dx, dy, dz] = [r.bb.max[0]-r.bb.min[0], r.bb.max[1]-r.bb.min[1], r.bb.max[2]-r.bb.min[2]].map(v=>+v.toFixed(3));
  const gap = +(r.bb.min[1] - TABLE_Y).toFixed(3);
  console.log(`## ${mid}: world=${dx}x${dy}x${dz}m ymin=${r.bb.min[1]} 距桌面间隙=${gap > 0 ? "+" + gap : gap}m scale=${r.scale} rot=${r.rotation} pos=${r.position} pins=${JSON.stringify(r.pins)}`);
}
console.log("PAGEERRORS:", errors.length, errors.slice(0, 3));
await browser.close();
srv.close();

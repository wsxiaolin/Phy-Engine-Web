// probe_scene.mjs — 实例化指定元件后 dump 场景 mesh 清单（名称/几何/尺寸/ymin）
// 用法: node probe_scene.mjs "Comparator"
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
await new Promise((r) => srv.listen(8956, r));

const modelId = process.argv[2] || "Comparator";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 720, height: 720 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://localhost:8956/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.addStyleTag({ content: "#brand,#left-tools,#right-tools,#perf,#wirebar,#palette,#inspector,#toast{display:none!important}" });

const dump = await page.evaluate(async (mid) => {
  const app = window.__app;
  app.reset();
  const e = app.experiment.addElement({ modelId: mid, label: "", position: { x: 0, y: 0.78, z: 0 }, properties: {} });
  await app.instantiate(e);
  const g = app.elementObjects.get(e.id);
  const out = [];
  g.updateWorldMatrix(true, true);
  g.traverse((o) => {
    if (!o.isMesh) return;
    let geo = "external";
    if (o.geometry) {
      if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
      const bb = o.geometry.boundingBox;
      const size = [bb.max.x-bb.min.x, bb.max.y-bb.min.y, bb.max.z-bb.min.z].map((v)=>Math.round(v*1000)/1000);
      const t = o.geometry.attributes.position ? o.geometry.attributes.position.count : 0;
      geo = `verts=${t} size=${size}`;
    }
    const e = o.matrixWorld.elements;
    const p = { x: e[12], y: e[13], z: e[14] };
    out.push({ name: o.name, parent: o.parent?.name || "", geo,
      pos: [p.x, p.y, p.z].map((v) => Math.round(v*1000)/1000),
      mat: (Array.isArray(o.material) ? o.material.map((m)=>m.name||m.color?.getHexString()) : [o.material?.name || o.material?.color?.getHexString()]).join(","),
      visible: o.visible });
  });
  return out;
}, modelId);
console.log(JSON.stringify(dump, null, 1));
console.log("PAGEERRORS:", errors.length, errors);
await browser.close();
srv.close();

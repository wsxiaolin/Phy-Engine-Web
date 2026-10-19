// 解剖 GLB：节点树 + 逐 mesh 世界包围盒 + 可见性/材质
// 用法: node glb_inspect.mjs Basic_Capacitor.glb
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const WEB = process.cwd();
const ROOT = join(WEB, "..");
const srv = createServer((req, res) => {
  let p = req.url.split("?")[0];
  let base = WEB;
  if (p.startsWith("/assets/")) { base = ROOT; p = "/build" + p; }
  else if (p === "/") p = "/refshot.html";
  const f = join(base, p);
  try {
    const data = readFileSync(f);
    const ext = f.slice(f.lastIndexOf("."));
    const MIME = { ".html": "text/html", ".js": "text/javascript", ".glb": "model/gltf-binary", ".json": "application/json" };
    res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
    res.end(data);
  } catch { res.writeHead(404); res.end(); }
});
await new Promise((r) => srv.listen(8954, r));

const { chromium } = await import("playwright");
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 720, height: 720 } });
page.on("console", (m) => console.log("[console]", m.text()));
await page.goto("http://localhost:8954/", { waitUntil: "networkidle" });

const glb = process.argv[2];
const info = await page.evaluate(async (u) => {
  const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
  const loader = new GLTFLoader();
  const gltf = await loader.loadAsync(u);
  const root = gltf.scene;
  root.updateWorldMatrix(true, true);
  const nodes = [];
  root.traverse((o) => {
    const rec = { name: o.name, type: o.type };
    if (o.matrix) { const e = o.matrixWorld.elements; rec.pos = [+e[12].toFixed(4), +e[13].toFixed(4), +e[14].toFixed(4)]; }
    if (o.visible === false) rec.visible = false;
    if (o.geometry) {
      if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
      const bb = o.geometry.boundingBox, e = o.matrixWorld.elements;
      const mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9];
      const cs = [[bb.min.x,bb.min.y,bb.min.z],[bb.min.x,bb.min.y,bb.max.z],[bb.min.x,bb.max.y,bb.min.z],[bb.min.x,bb.max.y,bb.max.z],[bb.max.x,bb.min.y,bb.min.z],[bb.max.x,bb.min.y,bb.max.z],[bb.max.x,bb.max.y,bb.min.z],[bb.max.x,bb.max.y,bb.max.z]];
      for (const p of cs) for (let i = 0; i < 3; i++) {
        const v = e[i]*p[0] + e[4+i]*p[1] + e[8+i]*p[2] + e[12+i];
        mn[i] = Math.min(mn[i], v); mx[i] = Math.max(mx[i], v);
      }
      rec.meshBB = { min: mn.map((v) => +v.toFixed(4)), max: mx.map((v) => +v.toFixed(4)), size: [mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2]].map((v) => +v.toFixed(4)) };
      rec.mat = o.material ? (Array.isArray(o.material) ? o.material.map((m) => `${m.type}:${m.visible === false ? "HIDDEN" : "ok"}:${(m.map || null) && m.map.image ? "tex" : (m.color ? "#" + m.color.getHexString() : "?")}`) : `${o.material.type}:${o.material.visible === false ? "HIDDEN" : "ok"}:${(o.material.map || null) && o.material.map.image ? "tex" : (o.material.color ? "#" + o.material.color.getHexString() : "?")}`) : null;
      rec.vs = o.geometry.attributes.position ? o.geometry.attributes.position.count : 0;
    }
    nodes.push(rec);
  });
  return { nodes };
}, `/assets/components/${glb}`);
console.log(JSON.stringify(info, null, 1));
await browser.close();
srv.close();

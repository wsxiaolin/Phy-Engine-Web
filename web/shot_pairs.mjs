// web 端单元件截图：36 个 supported 元件逐件取景 → ../build/webshot/{id}.png
// 用法: cd web && node shot_pairs.mjs（需先 npm run build 同步 dist 资产）
// 已存在的 {id}.png 自动跳过（断点续跑），FORCE=1 全量重截
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFileSync, existsSync, mkdirSync } from "node:fs";
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
await new Promise((r) => srv.listen(8952, r));

const SUPPORTED = new Set(["Ground Component", "Resistor", "Basic Capacitor", "Basic Inductor", "Battery Source", "Simple Switch", "Push Switch", "Air Switch", "Transformer", "Mutual Inductor", "Rectifier", "Logic Input", "Logic Output", "Or Gate", "And Gate", "Nand Gate", "Nor Gate", "Xor Gate", "Xnor Gate", "Imp Gate", "Nimp Gate", "Yes Gate", "No Gate", "Schmitt Trigger", "Comparator", "JK Flipflop", "T Flipflop", "Real-T Flipflop", "Multiplier", "D Flipflop", "Half Adder", "Full Adder", "Half Subtractor", "Full Subtractor", "Counter", "Random Generator", ...(process.env.EXTRA ? process.env.EXTRA.split(',') : [])]);
const cat = JSON.parse(readFileSync(join(process.cwd(), "../build/assets/catalog.json"), "utf8"));
const items = cat.items || cat;
const names = items.filter((i) => SUPPORTED.has(i.ModelID)).map((i) => i.ModelID);
mkdirSync(join(process.cwd(), "../build/webshot"), { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 720, height: 720 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://localhost:8952/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
// 隐藏 HUD 铬件，只留场景画布与元件标签
await page.addStyleTag({ content: "#brand,#left-tools,#right-tools,#perf,#wirebar,#palette,#inspector,#toast{display:none!important}" });

// 页内 vanilla 世界包围盒（不依赖暴露 THREE 全局）
// visible 过滤：不可见辅助几何（碰撞体/占位）不撑大 bbox
const pageHelpers = `
window.__worldBox = (g) => {
  g.updateWorldMatrix(true, true);
  const mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9];
  g.traverse((o) => {
    if (!o.geometry || !o.visible) return;
    if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
    const bb = o.geometry.boundingBox;
    const e = o.matrixWorld.elements;
    const cs = [[bb.min.x,bb.min.y,bb.min.z],[bb.min.x,bb.min.y,bb.max.z],[bb.min.x,bb.max.y,bb.min.z],[bb.min.x,bb.max.y,bb.max.z],
                [bb.max.x,bb.min.y,bb.min.z],[bb.max.x,bb.min.y,bb.max.z],[bb.max.x,bb.max.y,bb.min.z],[bb.max.x,bb.max.y,bb.max.z]];
    for (const p of cs) for (let i = 0; i < 3; i++) {
      const v = e[i]*p[0] + e[4+i]*p[1] + e[8+i]*p[2] + e[12+i];
      mn[i] = Math.min(mn[i], v); mx[i] = Math.max(mx[i], v);
    }
  });
  return { min: mn, max: mx };
};
// 屏幕空间精确取景：bbox 8 角点对每轴解析求最小距离，使全部角点投进
// 90% 视口内。取代旧 max 边×√3/2 包围球法（扁件虚大最多 ~50% 元件
// 太小 → VLM 判定漂移，MI/Relay 两案销案时的共同诱因，round-23 根治）。
window.__frame = (bb, dir) => {
  const app = window.__app;
  const cam = app.world.camera, ctl = app.world.controls;
  const t = [(bb.min[0]+bb.max[0])/2, (bb.min[1]+bb.max[1])/2, (bb.min[2]+bb.max[2])/2];
  const M = 0.90; // 元件占视口 90%（留 10% 边距呼吸）
  const fovY = (cam.fov * Math.PI) / 180;
  const tanY = Math.tan(fovY / 2);
  const tanX = tanY * cam.aspect;
  const dl = Math.hypot(dir.x, dir.y, dir.z);
  const d = [dir.x/dl, dir.y/dl, dir.z/dl]; // 相机位于 target + d*dist
  // OrbitControls 不滚转，camera.up 恒为世界 up (0,1,0)
  let r = [d[2], 0, -d[0]];
  const rl = Math.hypot(r[0], r[1], r[2]) || 1;
  r = [r[0]/rl, r[1]/rl, r[2]/rl];
  const u = [r[2]*d[1]-r[1]*d[2], r[0]*d[2]-r[2]*d[0], r[1]*d[0]-r[0]*d[1]]; // r×forward = up
  let dist = 0.05;
  for (let ci = 0; ci < 8; ci++) {
    const p = [(ci&1?bb.max[0]:bb.min[0]), (ci&2?bb.max[1]:bb.min[1]), (ci&4?bb.max[2]:bb.min[2])];
    const o = [p[0]-t[0], p[1]-t[1], p[2]-t[2]];
    const depth = o[0]*d[0] + o[1]*d[1] + o[2]*d[2];
    const rx = o[0]*r[0] + o[1]*r[1] + o[2]*r[2];
    const ry = o[0]*u[0] + o[1]*u[1] + o[2]*u[2];
    dist = Math.max(dist, depth + 0.01,
                    depth + Math.abs(rx) / (M * tanX),
                    depth + Math.abs(ry) / (M * tanY));
  }
  cam.position.set(t[0] + d[0]*dist, t[1] + d[1]*dist, t[2] + d[2]*dist);
  ctl.target.set(t[0], t[1], t[2]);
  ctl.update();
};
`;
await page.evaluate(pageHelpers);

const DIR = { x: 0.62, y: 0.55, z: 0.9 };   // 与 refshot.html 一致（3/4 视角）
const FORCE = !!process.env.FORCE;
const ONLY = process.env.ONLY ? new Set(process.env.ONLY.split(',')) : null;
let ok = 0, skip = 0;
for (const id of names) {
  if (ONLY && !ONLY.has(id)) continue;
  const out = join(process.cwd(), `../build/webshot/${id.replace(/ /g, "_")}.png`);
  if (!FORCE && existsSync(out)) { console.log("skip", id); skip++; ok++; continue; }
  try {
    await page.evaluate(async (modelId) => {
      const app = window.__app;
      app.reset();
      const e = app.experiment.addElement({ modelId, label: "", position: { x: 0, y: 0.78, z: 0 }, properties: {} });
      await app.instantiate(e);
      const g = app.elementObjects.get(e.id);
      window.__frame(window.__worldBox(g), { x: 0.62, y: 0.55, z: 0.9 });
    }, id);
    await page.waitForTimeout(250);
    await page.screenshot({ path: out });
    ok++;
    console.log("webshot", id);
  } catch (e) {
    console.log("FAIL", id, e.message);
    errors.push(`${id}: ${e.message}`);
  }
}
console.log(`DONE ${ok}/${names.length} PAGEERRORS:${errors.length}`);
await browser.close();
srv.close();

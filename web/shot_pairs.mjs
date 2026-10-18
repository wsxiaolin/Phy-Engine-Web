// web 端单元件截图：36 个 supported 元件逐件取景 → ../build/webshot/{id}.png
// 用法: cd web && node shot_pairs.mjs（需先 npm run build 同步 dist 资产）
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

const SUPPORTED = new Set(["Ground Component", "Resistor", "Basic Capacitor", "Basic Inductor", "Battery Source", "Simple Switch", "Push Switch", "Air Switch", "Transformer", "Mutual Inductor", "Rectifier", "Logic Input", "Logic Output", "Or Gate", "And Gate", "Nand Gate", "Nor Gate", "Xor Gate", "Xnor Gate", "Imp Gate", "Nimp Gate", "Yes Gate", "No Gate", "Schmitt Trigger", "Comparator", "JK Flipflop", "T Flipflop", "Real-T Flipflop", "Multiplier", "D Flipflop", "Half Adder", "Full Adder", "Half Subtractor", "Full Subtractor", "Counter", "Random Generator"]);
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
const pageHelpers = `
window.__worldBox = (g) => {
  g.updateWorldMatrix(true, true);
  const mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9];
  g.traverse((o) => {
    if (!o.geometry) return;
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
window.__frame = (bb, dir) => {
  const app = window.__app;
  const cam = app.world.camera, ctl = app.world.controls;
  const c = [(bb.min[0]+bb.max[0])/2, (bb.min[1]+bb.max[1])/2, (bb.min[2]+bb.max[2])/2];
  const s = [bb.max[0]-bb.min[0], bb.max[1]-bb.min[1], bb.max[2]-bb.min[2]];
  const radius = Math.max(s[0], s[1], s[2], 0.01) * 0.5 * Math.sqrt(3);
  const fovY = (cam.fov * Math.PI) / 180, fovX = 2 * Math.atan(Math.tan(fovY / 2) * cam.aspect);
  const dist = radius / Math.tan(Math.min(fovY, fovX) / 2) * 1.12;
  const dl = Math.hypot(dir.x, dir.y, dir.z);
  cam.position.set(c[0] + dir.x / dl * dist, c[1] + dir.y / dl * dist, c[2] + dir.z / dl * dist);
  ctl.target.set(c[0], c[1], c[2]);
  ctl.update();
};
`;
await page.evaluate(pageHelpers);

const DIR = { x: 0.62, y: 0.55, z: 0.9 };   // 与 refshot.html 一致（3/4 视角）
let ok = 0;
for (const id of names) {
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
    await page.screenshot({ path: join(process.cwd(), `../build/webshot/${id.replace(/ /g, "_")}.png`) });
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

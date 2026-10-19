// catalog pin 坐标 vs GLB 几何世界包围盒 一致性校验（回归工具）
// 判定：pin 应落在主体包围盒外扩 MARGIN 内（接线柱长在主体上），
//       且 pin 不应深陷主体内部（穿模）或远离主体（脱节）。
// 用法: node pin_check.mjs            # 全部 catalog 元件
//       node pin_check.mjs Air_Switch Basic_Capacitor   # 指定 ModelID
// 输出: ../build/pin_check.json（逐元件 maxGap / sunken / detached）
import { createServer } from "node:http";
import { readFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const WEB = process.cwd();
const ROOT = join(WEB, "..");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".glb": "model/gltf-binary", ".json": "application/json" };
const srv = createServer((req, res) => {
  let p = req.url.split("?")[0];
  let base = WEB;
  if (p.startsWith("/assets/")) { base = ROOT; p = "/build" + p; }
  else if (p === "/") p = "/refshot.html";
  const f = join(base, p);
  try {
    const data = readFileSync(f);
    res.writeHead(200, { "Content-Type": MIME[f.slice(f.lastIndexOf("."))] || "application/octet-stream" });
    res.end(data);
  } catch { res.writeHead(404); res.end(); }
});
await new Promise((r) => srv.listen(8956, r));

const cat = JSON.parse(readFileSync(join(ROOT, "build/assets/catalog.json"), "utf8"));
const items = cat.items || cat;
const only = process.argv.slice(2);
const list = only.length ? items.filter((i) => only.includes(i.ModelID)) : items;

const MARGIN = 0.025;   // pin 允许在主体包围盒外 2.5cm 内（接线柱凸出）
const POST_H = 0.022;   // 与 src/components.js POST_H 一致：柱体贡献的高度

const browser = await (await import("playwright")).chromium.launch();
const page = await browser.newPage();
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
await page.goto("http://localhost:8956/", { waitUntil: "networkidle" });

const report = {};
let bad = 0;
for (const it of list) {
  const url = `/assets/components/${it.glb}`;
  if (!existsSync(join(ROOT, "build/assets/components", it.glb))) { console.log("SKIP", it.ModelID, "no glb"); continue; }
  const r = await page.evaluate(async ([u, pins]) => {
    const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
    const loader = new GLTFLoader();
    const gltf = await loader.loadAsync(u);
    const root = gltf.scene;
    root.updateWorldMatrix(true, true);
    const { Box3, Vector3 } = await import("three");
    const box = new Box3().setFromObject(root);
    const rows = [];
    for (const p of pins) {
      const [px, py, pz] = p.position;
      // 到包围盒的有符号间隙（<0 = 在盒内深度）
      const gap = {
        x: Math.max(box.min.x - px, px - box.max.x, 0),
        y: Math.max(box.min.y - py, py - box.max.y, 0),
        z: Math.max(box.min.z - pz, pz - box.max.z, 0),
      };
      rows.push({ name: p.name, pos: p.position, gap, dist: Math.hypot(gap.x, gap.y, gap.z) });
    }
    return {
      bb: { min: [+box.min.x.toFixed(4), +box.min.y.toFixed(4), +box.min.z.toFixed(4)],
            max: [+box.max.x.toFixed(4), +box.max.y.toFixed(4), +box.max.z.toFixed(4)] },
      size: [+box.max.x - +box.min.x, +box.max.y - +box.min.y, +box.max.z - +box.min.z].map((v) => +v.toFixed(4)),
      pins: rows,
    };
  }, [url, it.pins || []]);

  const maxDist = Math.max(0, ...r.pins.map((p) => p.dist));
  const h = Math.max(1e-6, r.bb.max[1] - r.bb.min[1]);
  r.pinYRel = r.pins.map((p) => +((p.pos[1] - r.bb.min[1]) / h).toFixed(2)); // 0=盒底 1=盒顶
  const sunken = r.pins.some((p) => p.gap.y === 0 && p.pos[1] < r.bb.min[1] + 0.005);
  const detached = maxDist > MARGIN;
  r.maxDist = +maxDist.toFixed(4);
  r.verdict = detached ? "DETACHED" : sunken ? "SUNKEN" : "OK";
  if (r.verdict !== "OK") bad++;
  report[it.ModelID] = r;
  console.log(`${r.verdict.padEnd(9)} ${it.ModelID.padEnd(24)} maxGap=${(maxDist * 1000).toFixed(1)}mm size=${r.size.map((v) => (v * 100).toFixed(1)).join("x")}cm`);
}

mkdirSync(join(ROOT, "build"), { recursive: true });
const fs = await import("node:fs");
fs.writeFileSync(join(ROOT, "build/pin_check.json"), JSON.stringify(report, null, 1));
console.log(`\nDONE ${list.length} checked, ${bad} problematic → build/pin_check.json`);
await browser.close();
srv.close();

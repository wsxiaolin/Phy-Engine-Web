// 批量元件截图：36 个 supported 元件，每屏 6 个（2×3），输出 build/grid_N.png
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
await new Promise((r) => srv.listen(8951, r));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://localhost:8951/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
const SUPPORTED = new Set(["Ground Component", "Resistor", "Basic Capacitor", "Basic Inductor", "Battery Source", "Simple Switch", "Push Switch", "Air Switch", "Transformer", "Mutual Inductor", "Rectifier", "Logic Input", "Logic Output", "Or Gate", "And Gate", "Nand Gate", "Nor Gate", "Xor Gate", "Xnor Gate", "Imp Gate", "Nimp Gate", "Yes Gate", "No Gate", "Schmitt Trigger", "Comparator", "JK Flipflop", "T Flipflop", "Real-T Flipflop", "Multiplier", "D Flipflop", "Half Adder", "Full Adder", "Half Subtractor", "Full Subtractor", "Counter", "Random Generator"]);
const catJson = JSON.parse(readFileSync(join(process.cwd(), "../build/assets/catalog.json"), "utf8"));
const items = catJson.items || catJson;
const names = items.filter((i) => SUPPORTED.has(i.ModelID)).map((i) => ({ id: i.ModelID, label: i.FriendlyName || i.ModelID }));
console.log("batch:", names.length, JSON.stringify(names.slice(0, 3)));
for (let g = 0; g * 6 < names.length; g++) {
  const group = names.slice(g * 6, g * 6 + 6);
  await page.evaluate(async (group) => {
    const app = window.__app;
    app.reset();
    const cx = [0.22, -0.22];
    const cz = [-0.3, 0, 0.3];
    for (let i = 0; i < group.length; i++) {
      const e = app.experiment.addElement({ modelId: group[i].id, label: group[i].label, position: { x: cx[i % 2], y: 0.78, z: cz[Math.floor(i / 2)] }, properties: {} });
      await app.instantiate(e);
    }
    const cam = app.world.camera, c = app.world.controls;
    cam.position.set(0, 1.35, 0.62);
    c.target.set(0, 0.8, 0);
    c.update();
  }, group);
  await page.waitForTimeout(600);
  await page.screenshot({ path: `../build/grid_${g}.png` });
  console.log("shot", g, group.map((x) => x.label).join(","));
}
console.log("PAGEERRORS:", errors.length, errors[0] || "");
await browser.close();
srv.close();

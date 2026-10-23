// Unity 源数据渲染：逐 GLB 中性影棚截图 → ../build/refshot/{id}.png
// 用法: cd web && node refshot.mjs [id1 id2 ...]（无参 = 全部 catalog 87 件）
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFileSync, existsSync, mkdirSync } from "node:fs";
import { join, extname } from "node:path";

const WEB = process.cwd();               // web/
const ROOT = join(WEB, "..");            // repo 根（build/assets 在此）
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".glb": "model/gltf-binary" };
const srv = createServer((req, res) => {
  let p = req.url.split("?")[0];
  let base = WEB;
  if (p.startsWith("/assets/")) { base = ROOT; p = "/build" + p; }
  else if (p === "/") p = "/refshot.html";
  const f = join(base, p);
  if (!existsSync(f) || !f.startsWith(base)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": MIME[extname(f)] || "application/octet-stream" });
  res.end(readFileSync(f));
});
await new Promise((r) => srv.listen(8953, r));

const cat = JSON.parse(readFileSync(join(ROOT, "build/assets/catalog.json"), "utf8"));
const items = cat.items || cat;
const chips = JSON.parse(readFileSync(join(ROOT, "build/assets/chips.json"), "utf8"));
// 复刻 src/catalog.js pinsOf：entry.pins 优先（与 GLB 节点矩阵同源），芯片类走
// ChipComponent 公式兜底（outputs x=+0.065 / inputs x=-0.065，z=lerp，GLB 镜像空间）。
function pinsOf(modelId) {
  const entry = items.find((e) => e.ModelID === modelId);
  if (!entry) return [];
  if (entry.pins && entry.pins.length) {
    return entry.pins.map((p, i) => ({ name: p.name || `Pin ${i + 1}`, position: p.position, isPositive: !!p.isPositive }));
  }
  const spec = chips[modelId];
  if (!spec) return [];
  const zLerp = (i, n) => (n <= 1 ? 0 : -0.07 + (0.14 * i) / (n - 1));
  const outN = spec.outputs.length, inN = spec.inputs.length;
  const pins = [];
  for (let i = 0; i < outN; i++) pins.push({ name: spec.pins[spec.outputs[i]], position: [0.065, 0.02, zLerp(i, outN)], isPositive: true });
  for (let i = 0; i < inN; i++) pins.push({ name: spec.pins[spec.inputs[i]], position: [-0.065, 0.02, zLerp(i, inN)], isPositive: false });
  return pins;
}
const only = process.argv.slice(2);
const names = (only.length ? items.filter((i) => only.includes(i.ModelID)) : items)
  .map((i) => ({ id: i.ModelID, glb: i.glb }));
mkdirSync(join(ROOT, "build/refshot"), { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 720, height: 720 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://localhost:8953/", { waitUntil: "networkidle" });
let ok = 0;
for (const n of names) {
  const url = `/assets/components/${n.glb}`;
  if (!existsSync(join(ROOT, "build/assets/components", n.glb))) { console.log("SKIP", n.id, "no glb"); continue; }
  try {
    const pins = pinsOf(n.id);
    await page.evaluate(async ({ u, pins }) => { await window.loadGlb(u, pins); }, { u: url, pins });
    await page.waitForTimeout(120);
    await page.screenshot({ path: join(ROOT, `build/refshot/${n.id.replace(/ /g, "_")}.png`) });
    ok++;
    console.log("refshot", n.id);
  } catch (e) {
    console.log("FAIL", n.id, e.message);
    errors.push(`${n.id}: ${e.message}`);
  }
}
console.log(`DONE ${ok}/${names.length} PAGEERRORS:${errors.length}`);
await browser.close();
srv.close();

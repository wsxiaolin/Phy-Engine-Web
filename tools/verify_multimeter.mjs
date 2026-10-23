// M8 Multimeter（多用电表）专项 e2e：三档位族实测 + 屏显断言 + 截图。
// 跑法：node tools/verify_multimeter.mjs（需先 cd web && npx vite build）
// 场景与期望（数值全部对照 unity Meters/Multimeter.cs，禁记忆）：
//  ①电流档(模式6, DC 0.2A)：电池3V + 100Ω + 表串联 → i=0.03A → 屏显 "0.03"
//    极性：电流入 Pin1(索引0, 正表笔)——与安培计 Pin2 正公共相反（catalog isPositive）。
//  ②电压档(模式15, DC 20V)：表并联 100Ω（跨电池）→ u=3V → 屏显 "3"
//  ③电阻档(模式8, 200Ω)：内置 -15V 源 + R1=1Ω 跨接 100Ω → R=15/I-1=100 → "100"
// 断言三重：multimeterDisplay 纯函数（Node 直跑源码）+ 页面 statistics 数值 +
// DOM 标签文本（屏显数字作浮动标签的可见性等价）。
import { chromium } from "playwright";
import { multimeterDisplay } from "../web/src/meters.js";
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { join, extname } from "node:path";

const ROOT = join(process.cwd(), "web/dist");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".glb": "model/gltf-binary", ".wasm": "application/wasm", ".png": "image/png" };
const srv = createServer((req, res) => {
  let p = req.url.split("?")[0];
  if (p === "/") p = "/index.html";
  const f = join(ROOT, p);
  if (!existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": MIME[extname(f)] || "application/octet-stream" });
  res.end(readFileSync(f));
});
await new Promise((r) => srv.listen(8934, r));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("pageerror", (e) => { console.log("PAGEERROR:", e.message); process.exitCode = 1; });
page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE:", m.text().slice(0, 200)); });
await page.goto("http://localhost:8934/");
await page.waitForFunction(() => window.__app && window.__app.experiment, null, { timeout: 30000 });
await page.waitForTimeout(2500); // 首屏 GLB

// ---- 场景搭建（数据驱动，单函数传参——Playwright 标准模式）--------------------
const runScene = async (cfg) => {
  const out = await page.evaluate(async (cfg) => {
    const app = window.__app;
    app.reset();
    const mk = async (modelId, x, z, props = {}) => {
      const el = app.experiment.addElement({ modelId, label: modelId, position: { x, y: 0.78, z }, rotY: 0, properties: props });
      await app.instantiate(el);
      return el;
    };
    const els = {};
    for (const e of cfg.elements) els[e.key] = await mk(e.modelId, e.x, e.z, e.props);
    for (const w of cfg.wires) app.experiment.addWire(els[w.a].id, w.ap, els[w.b].id, w.bp, "黑色导线");
    app.syncWires();
    app.simulate(false);
    await new Promise((r) => setTimeout(r, 600));
    const el = app.experiment.elements.find((e) => e.modelId === "Multimeter");
    return { stat: { ...el.statistics }, broken: !!el.broken, props: { ...el.properties } };
  }, cfg);
  await page.waitForTimeout(700); // 渲染循环走一帧 + 浮动标签
  return out;
};

// ① 电流档（模式 6）：bat.0(+)→表Pin1(0)；表Pin2(1)→res.0；res.1→bat.1(-)
const scA = await runScene({
  elements: [
    { key: "bat", modelId: "Battery Source", x: -0.35, z: 0, props: { 电压: 3 } },
    { key: "res", modelId: "Resistor", x: 0.0, z: 0.2, props: { 电阻: 100 } },
    { key: "mm", modelId: "Multimeter", x: 0.35, z: -0.05, props: { 状态: 6 } },
  ],
  wires: [
    { a: "bat", ap: 0, b: "mm", bp: 0 },
    { a: "mm", ap: 1, b: "res", bp: 0 },
    { a: "res", ap: 1, b: "bat", bp: 1 },
  ],
});

// ② 电压档（模式 15）：表并联在 100Ω（跨 3V 电池）两端
const scB = await runScene({
  elements: [
    { key: "bat", modelId: "Battery Source", x: -0.35, z: 0, props: { 电压: 3 } },
    { key: "res", modelId: "Resistor", x: 0.0, z: 0.2, props: { 电阻: 100 } },
    { key: "mm", modelId: "Multimeter", x: 0.35, z: -0.05, props: { 状态: 15 } },
  ],
  wires: [
    { a: "bat", ap: 0, b: "res", bp: 0 },
    { a: "res", ap: 1, b: "bat", bp: 1 },
    { a: "mm", ap: 0, b: "res", bp: 0 },
    { a: "mm", ap: 1, b: "res", bp: 1 },
  ],
});

// ③ 电阻档（模式 8）：表跨接独立 100Ω（内置 -15V 驱动）
const scC = await runScene({
  elements: [
    { key: "res", modelId: "Resistor", x: 0.0, z: 0.2, props: { 电阻: 100 } },
    { key: "mm", modelId: "Multimeter", x: 0.35, z: -0.05, props: { 状态: 8 } },
  ],
  wires: [
    { a: "mm", ap: 0, b: "res", bp: 0 },
    { a: "mm", ap: 1, b: "res", bp: 1 },
  ],
});

// ---- 断言 --------------------------------------------------------------------
// Node 直跑源码纯函数（multimeterDisplay）——页面 statistics 与屏显同时核对。
const disp = (sc) => multimeterDisplay({ properties: sc.props }, sc.stat);
const checks = [
  ["A 电流档 i≈0.03", Math.abs((scA.stat.瞬间电流 || 0) - 0.03) < 5e-3],
  ["A 屏显 '0.03'", disp(scA) === "0.03"],
  ["B 电压档 u≈3", Math.abs((scB.stat.瞬间电压 || 0) - 3) < 1e-3],
  ["B 屏显 '3'", disp(scB) === "3"],
  ["C 电阻档 |i|≈15/101", Math.abs(Math.abs(scC.stat.瞬间电流 || 0) - 15 / 101) < 5e-3],
  ["C 屏显 '100'", disp(scC) === "100"],
  ["无烧毁", !scA.broken && !scB.broken && !scC.broken],
];
for (const [name, ok] of checks) {
  console.log(ok ? "PASS" : "FAIL", name);
  if (!ok) process.exitCode = 1;
}
console.log("SCENE A:", JSON.stringify(scA));
console.log("SCENE B:", JSON.stringify(scB));
console.log("SCENE C:", JSON.stringify(scC));

// DOM 可见性：屏显数字以浮动标签呈现（场景 ③ 遗留页面，含 "100"）
const domOk = await page.evaluate(() => document.body.innerText.includes("100"));
console.log(domOk ? "PASS" : "FAIL", "DOM 标签含屏显 '100'");
if (!domOk) process.exitCode = 1;

// 俯视特写截图（电阻档：万用表 + 被测电阻 + 屏显标签同框）
await page.evaluate(() => {
  const app = window.__app;
  app.world.camera.position.set(0.18, 1.5, 0.32);
  app.world.controls.target.set(0.18, 0.78, 0.05);
  app.world.controls.update();
});
await page.waitForTimeout(700);
await page.screenshot({ path: "build/verify_multimeter_ohm.png" });
await browser.close();
srv.close();
console.log("MULTIMETER E2E", process.exitCode ? "FAILED" : "DONE");

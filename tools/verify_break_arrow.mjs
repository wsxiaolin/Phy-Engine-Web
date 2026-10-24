// M8 烧毁警示视觉 e2e（Unity CircuitComponent.RenderArrow / RepairComponent 一比一）。
// 跑法：node tools/verify_break_arrow.mjs（内起 http 服务 + playwright，加载 web/dist）
// 场景：电池 3V → 1MΩ 电阻 → 灵敏电流计（3µA 满偏，不烧）→ 切电阻 100Ω
// （15mA，刻度 5000 超 ±1.05 烧毁）→ 验证红箭头/位置/动画 → 切回 1MΩ + repair → 恢复。
// Unity 权威参数：Arrow.FBX 几何、Arrow-Broken.mat 纯红、y=0.07、
// Arrow Animation.anim 2s 浮动 ±0.03、Button-Repair 仅 IsBroken 时出现。
import { chromium } from "playwright";
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

const probe = () => page.evaluate(() => {
  const app = window.__app;
  for (const [id, g] of app.elementObjects) {
    const el = app.experiment.getElement(id);
    if (el && el.modelId === "Galvanometer") {
      const a = g.userData.arrow;
      return {
        broken: !!el.broken,
        stat: el.statistics,
        arrow: a ? {
          visible: a.visible,
          color: a.material.color.getHex(),
          y: +a.position.y.toFixed(4),
          hasFloat: a.position.y >= 0.07 && a.position.y <= 0.1001,
        } : null,
      };
    }
  }
  return null;
});

// 搭电路：3V + 1MΩ + 灵敏电流计（Pin2 正入 Pin1 负出）
await page.evaluate(async () => {
  const app = window.__app;
  app.reset();
  const mk = async (modelId, x, z, props = {}) => {
    const el = app.experiment.addElement({ modelId, label: modelId, position: { x, y: 0.78, z }, rotY: 0, properties: props });
    await app.instantiate(el);
    return el;
  };
  const bat = await mk("Battery Source", -0.35, 0, { 电压: 3 });
  const res = await mk("Resistor", 0.0, 0.2, { 电阻: 1e6 });
  const gal = await mk("Galvanometer", 0.35, -0.05);
  app.experiment.addWire(bat.id, 1, res.id, 0, "红色导线");
  app.experiment.addWire(res.id, 1, gal.id, 1, "黑色导线");
  app.experiment.addWire(gal.id, 0, bat.id, 0, "黑色导线");
  app.syncWires();
  app.simulate(false);
});
await page.waitForTimeout(600);

// 阶段 1：满偏不烧 → 箭头隐藏
let s = await probe();
const ok1 = !s.broken && s.arrow && !s.arrow.visible;
console.log("PHASE1 not-broken:", ok1 ? "PASS" : "FAIL", JSON.stringify(s));
if (!ok1) process.exitCode = 1;

// 阶段 2：切电阻 100Ω → 30mA → 刻度 -10 → 烧毁（轮询等待，防主线程忙致 timer 晚触发）
await page.evaluate(() => {
  const app = window.__app;
  const res = app.experiment.elements.find((e) => e.modelId === "Resistor");
  res.properties["电阻"] = 100;
  app.scheduleSimulate();
});
const t2 = Date.now();
await page.waitForFunction(() => {
  const app = window.__app;
  const gal = app.experiment.elements.find((e) => e.modelId === "Galvanometer");
  return gal && gal.broken;
}, null, { timeout: 8000, polling: 100 }).catch(() => {});
console.log("PHASE2 wait:", Date.now() - t2, "ms");
s = await probe();
const ok2 = s.broken && s.arrow && s.arrow.visible
  && s.arrow.color === 0xff0000 && s.arrow.hasFloat
  && Math.abs(s.stat.刻度 || 0) > 1.05; // 3V/(100+100)Ω=15mA → 刻度5000，超±1.05即烧毁
console.log("PHASE2 broken+arrow:", ok2 ? "PASS" : "FAIL", JSON.stringify(s));
if (!ok2) process.exitCode = 1;

// 阶段 2b：broken 时检查面板出现「维修」按钮（Unity Button-Repair）
const hasRepairBtn = await page.evaluate(() => {
  const app = window.__app;
  const el = app.experiment.elements.find((e) => e.modelId === "Galvanometer");
  app.showInspector(el);
  const btns = [...document.querySelectorAll(".insp-actions button")].map((b) => b.textContent);
  return { btns, repair: btns.includes("维修") };
});
const ok2b = hasRepairBtn.repair;
console.log("PHASE2b repair-button:", ok2b ? "PASS" : "FAIL", JSON.stringify(hasRepairBtn));
if (!ok2b) process.exitCode = 1;

// 烧毁态俯视特写截图（红箭头 + 表盘 + 维修按钮同框）
await page.evaluate(() => {
  const app = window.__app;
  app.world.camera.position.set(0.15, 1.35, 0.55);
  app.world.controls.target.set(0.2, 0.78, 0.0);
  app.world.controls.update();
});
await page.waitForTimeout(700);
await page.screenshot({ path: "build/verify_break_arrow.png" });

// 阶段 3：切回 1MΩ（撤过载源）→ repair → 读数恢复 + 箭头隐藏（轮询等 stat 重算）
await page.evaluate(() => {
  const app = window.__app;
  const res = app.experiment.elements.find((e) => e.modelId === "Resistor");
  res.properties["电阻"] = 1e6;
  app.scheduleSimulate();
});
await page.waitForTimeout(600);
await page.evaluate(() => {
  const app = window.__app;
  const gal = app.experiment.elements.find((e) => e.modelId === "Galvanometer");
  app.repair(gal.id);
});
const t3 = Date.now();
await page.waitForFunction(() => {
  const app = window.__app;
  const gal = app.experiment.elements.find((e) => e.modelId === "Galvanometer");
  return gal && !gal.broken && gal.statistics && Number.isFinite(Number(gal.statistics["刻度"]));
}, null, { timeout: 8000, polling: 100 }).catch(() => {});
console.log("PHASE3 wait:", Date.now() - t3, "ms");
s = await probe();
const ok3 = !s.broken && s.arrow && !s.arrow.visible
  && Math.abs(Math.abs(s.stat.刻度 || 0) - 1) < 0.02;
console.log("PHASE3 repaired:", ok3 ? "PASS" : "FAIL", JSON.stringify(s));
if (!ok3) process.exitCode = 1;

await browser.close();
srv.close();
console.log("BREAK-ARROW E2E", process.exitCode ? "FAILED" : "DONE");

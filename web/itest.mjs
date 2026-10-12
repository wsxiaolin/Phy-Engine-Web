// 交互端到端：色选→连线颜色、点选导线→Delete 删除、开关切换、属性编辑
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
await new Promise((r) => srv.listen(8937, r));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://localhost:8937/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
const r = await page.evaluate(async () => {
  const app = window.__app;
  const out = {};
  app.reset();
  const mk = async (m, x, z, props) => { const e = app.experiment.addElement({ modelId: m, label: m, position: { x, y: 0.78, z }, properties: props }); await app.instantiate(e); return e; };
  const bat = await mk("Battery Source", -0.25, 0, { 电压: 3 });
  const res = await mk("Resistor", 0.2, 0, { 电阻: 100 });
  const sw = await mk("Simple Switch", 0, 0.25, { 开关: 0 });
  // 1) 色选：模拟色选回调
  app.wireColor = "红色导线";
  app.experiment.addWire(bat.id, 1, res.id, 0, app.wireColor);
  app.experiment.addWire(res.id, 1, bat.id, 0, "黑色导线");
  app.syncWires();
  out.wireColors = app.experiment.wires.map((w) => w.colorName);
  // 2) 导线选中/删除
  const view = [...app.wireSystem.views.values()].find((v) => v.mesh.userData.wire.colorName === "红色导线");
  app.selectWire(view);
  out.selWireHighlighted = app.rails.selWire === view;
  app.deleteSelectedWire();
  out.afterDelete = app.experiment.wires.length;
  // 补回红线（删除验证完成），恢复闭合回路
  app.experiment.addWire(bat.id, 1, res.id, 0, "红色导线");
  app.syncWires();
  // 绕行验证：红线上放一个电阻挡路（已同步 obstacles）
  // 3) 开关切换
  out.swBefore = sw.properties["开关"];
  app.toggleInteractive(sw.id);
  out.swAfter = sw.properties["开关"];
  // 4) 属性编辑→仿真（电阻改 50Ω → 电流 60mA）
  res.properties["电阻"] = 50;
  try { app.simulate(true); } catch (e) { out.simErr = String(e); }
  out.payloadWires = JSON.parse(app.engine.dump ? "{}" : "{}");
  { const d = app.engine.dump ? null : null; }
  // 直接读引擎 experiment 的 wires：dump 全量
  try { const dd = app.engine.dump(0); const root = JSON.parse(dd); const ss = JSON.parse((root.Experiment||root).StatusSave); out.engWires = ss.Wires; out.engEls = ss.Elements.map(e=>({i:e.Identifier,m:e.ModelID,p:e.Properties})); } catch(e2) { out.dumpErr = String(e2); }
  await new Promise((r2) => setTimeout(r2, 500));
  out.batStat = bat.statistics;
  out.lastSimErr = app.lastSimError || null;
  out.hasSim = app.hasSimulated;
  out.expect = "电流约 0.06";
  const dff = await mk("D Flipflop", -0.45, 0.3);
  const li = await mk("Logic Input", -0.55, -0.2, { "开关": 1 });
  app.experiment.addWire(li.id, 0, dff.id, 2, "绿色导线"); // D<-逻辑输入
  app.syncWires();
  try { app.simulate(true); out.clkOk = true; for (let i=0;i<3;i++) app.engine.digitalClk(); out.clkOk = true; } catch (e) { out.clkOk = String(e); }
  return out;
});
await page.evaluate(() => {
  const app = window.__app;
  const cam = app.world.camera, c = app.world.controls;
  cam.position.set(0, 1.6, 0.9); c.target.set(0, 0.78, 0); c.update();
});
await page.waitForTimeout(500);
await page.screenshot({ path: "../build/interact_final.png" });
console.log(JSON.stringify(r, null, 1));
console.log("PAGEERRORS:", errors.length, errors[0] || "");
await browser.close(); srv.close();

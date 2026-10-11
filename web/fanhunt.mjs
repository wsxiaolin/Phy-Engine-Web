import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { join, extname } from "node:path";
const ROOT = join(process.cwd(), "dist");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".glb": "model/gltf-binary", ".wasm": "application/wasm" };
const srv = createServer((req, res) => {
  let p = req.url.split("?")[0]; if (p === "/") p = "/index.html";
  const f = join(ROOT, p);
  if (!existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": MIME[extname(f)] || "application/octet-stream" });
  res.end(readFileSync(f));
});
await new Promise((r) => srv.listen(8936, r));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto("http://localhost:8936/", { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
const shot = async (name, hide) => {
  await page.evaluate((hide) => {
    const app = window.__app;
    app.reset();
    return (async () => {
      const mk = async (m, x, z, props) => { const e = app.experiment.addElement({ modelId: m, label: m, position: { x, y: 0.78, z }, properties: props }); await app.instantiate(e); return e; };
      const bat = await mk("Battery Source", 0, 0, { 电压: 3 });
      const res = await mk("Resistor", 0.25, 0, { 电阻: 100 });
      app.experiment.addWire(bat.id, 1, res.id, 0, "红色导线");
      app.experiment.addWire(res.id, 1, bat.id, 0, "黑色导线");
      app.syncWires();
      // 隐藏指定对象
      if (hide === "redwire" || hide === "blackwire") {
        const hex = hide === "redwire" ? 0xe0574a : 0x2b2b2b;
        app.wireSystem.group.traverse((o) => { if (o.isMesh && o.material.color.getHex() === hex) o.visible = false; });
      } else if (hide === "allwires") {
        app.wireSystem.group.visible = false;
      } else if (hide === "models") {
        for (const g of app.elementObjects.values()) g.getObjectByName("__model__") && (g.getObjectByName("__model__").visible = false);
      }
      const cam = app.world.camera, c = app.world.controls;
      cam.position.set(0.12, 1.2, 0.75); c.target.set(0.12, 0.8, 0); c.update();
    })();
  }, hide);
  await page.waitForTimeout(700);
  await page.screenshot({ path: `../build/fan_${name}.png` });
};
await shot("all", "none");
await shot("nored", "redwire");
await shot("noboth", "allwires");
console.log("done");
await browser.close(); srv.close();

// fps 探针：验证 headless 下 rAF 间隔与 HUD 结算行为。
// 端口 8961 独立于 shot_pairs 的 8952。
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
await new Promise((r) => srv.listen(8961, r));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 720, height: 720 } });
await page.goto("http://localhost:8961/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);

// 在页面里埋 rAF 间隔统计（独立于 app 的帧计数）
const raf = await page.evaluate(async () => {
  const ts = [];
  await new Promise((done) => {
    let n = 0;
    const tick = (t) => { ts.push(t); if (++n >= 10) done(); else requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
    setTimeout(done, 30000); // 兜底
  });
  const gaps = ts.slice(1).map((t, i) => t - ts[i]);
  return { count: ts.length, gaps: gaps.map((g) => Math.round(g)) };
});
const hudFps = await page.evaluate(() => document.getElementById("fps")?.textContent || "n/a");
console.log("headless rAF 10帧间隔(ms):", JSON.stringify(raf.gaps));
console.log("headless 平均 rAF fps:", raf.gaps.length ? (1000 / (raf.gaps.reduce((a, b) => a + b, 0) / raf.gaps.length)).toFixed(2) : "?");
console.log("HUD 读数:", hudFps);
await browser.close();
srv.close();

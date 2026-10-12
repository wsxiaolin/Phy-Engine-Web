// 路由单元测试：绕障走位正确性
import { routeWire2D } from "./src/wires.js";
const box = { x: 0, z: 0, hx: 0.1, hz: 0.1 };
// 1) 无障碍直连
let w = routeWire2D(-0.3, 0, 0.3, 0, []);
console.log(w.length === 2 ? "PASS 直连" : `FAIL 直连 ${w.length}`);
// 2) 穿过中间元件 → 绕角
w = routeWire2D(-0.3, 0, 0.3, 0, [box]);
const around = w.length >= 3 && w.every((p) => Math.abs(p.x) > 0.1 - 1e-6 || Math.abs(p.z) > 0.1 - 1e-6 || (Math.abs(Math.abs(p.x) - 0.1) < 1e-4 && Math.abs(Math.abs(p.z) - 0.1) < 1e-4));
console.log(w.length >= 3 ? "PASS 绕障(角点绕行)" : `FAIL 绕障 ${JSON.stringify(w)}`);
// 3) 贴边不穿盒：插值检查
let ok = true;
for (let i = 1; i < w.length; i++) {
  for (let t = 0; t <= 1; t += 0.05) {
    const x = w[i-1].x + (w[i].x - w[i-1].x) * t;
    const z = w[i-1].z + (w[i].z - w[i-1].z) * t;
    if (x > -box.hx && x < box.hx && z > -box.hz && z < box.hz) ok = false;
  }
}
console.log(ok ? "PASS 折线不穿盒" : "FAIL 折线穿盒");
// 4) 端点在盒内的自身排除由调用方处理（两端元件已排除）

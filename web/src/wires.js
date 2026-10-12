import * as THREE from "three";
import { WIRE_COLORS } from "./catalog.js";
import { pinWorld } from "./components.js";

export function wireColorHex(name) {
  const c = WIRE_COLORS.find((w) => w.name === name);
  return c ? c.hex : WIRE_COLORS[1].hex;
}

// ---- 平面路由，照抄 Unity CircuitWire.Reroute ------------------------------
// 起终直线撞到元件 AABB（xz 平面）→ 绕该盒 4 角中「价最小」的角，贪心迭代；
// 无障碍则直连。角点价 = 当前点→角 + 角→终点（Unity Prices 同构）。

function segHitsBox(ax, az, bx, bz, box) {
  const dx = bx - ax, dz = bz - az;
  let tmin = 0, tmax = 1;
  for (const axis of ["x", "z"]) {
    const h = axis === "x" ? box.hx : box.hz;
    const c = box[axis];
    const o = axis === "x" ? ax : az;
    const d = axis === "x" ? dx : dz;
    if (Math.abs(d) < 1e-9) {
      if (o < c - h || o > c + h) return false;
    } else {
      let t1 = (c - h - o) / d;
      let t2 = (c + h - o) / d;
      if (t1 > t2) [t1, t2] = [t2, t1];
      tmin = Math.max(tmin, t1);
      tmax = Math.min(tmax, t2);
      if (tmin > tmax) return false;
    }
  }
  return true;
}

function firstHit(ax, az, bx, bz, boxes) {
  for (const box of boxes) if (segHitsBox(ax, az, bx, bz, box)) return box;
  return null;
}

export function routeWire2D(sx, sz, tx, tz, obstacles) {
  const waypoints = [{ x: sx, z: sz }];
  let cx = sx, cz = sz;
  for (let guard = 0; guard < 64; guard++) {
    const hit = firstHit(cx, cz, tx, tz, obstacles);
    if (!hit) break;
    // 角点在检测盒角再外扩 4mm：下一段从角点出发不再贴盒
    const m = 0.004;
    const corners = [
      { x: hit.x - hit.hx - m, z: hit.z - hit.hz - m },
      { x: hit.x - hit.hx - m, z: hit.z + hit.hz + m },
      { x: hit.x + hit.hx + m, z: hit.z - hit.hz - m },
      { x: hit.x + hit.hx + m, z: hit.z + hit.hz + m },
    ];
    let best = -1;
    let bestPrice = Infinity;
    for (let i = 0; i < 4; i++) {
      const c = corners[i];
      if (waypoints.some((w) => Math.abs(w.x - c.x) < 1e-4 && Math.abs(w.z - c.z) < 1e-4)) continue;
      // 去程必须畅通：当前点→角点的线不得再穿任何盒（否则会选出对角穿越）
      if (firstHit(cx, cz, c.x, c.z, obstacles)) continue;
      const price = Math.hypot(c.x - cx, c.z - cz) + Math.hypot(c.x - tx, c.z - tz);
      if (price < bestPrice) {
        bestPrice = price;
        best = i;
      }
    }
    if (best < 0) break;
    cx = corners[best].x;
    cz = corners[best].z;
    waypoints.push(corners[best]);
  }
  waypoints.push({ x: tx, z: tz });
  return waypoints;
}

// 悬链高度，照抄 Unity CircuitWire.Render：
//   A = 60/log10(len_cm)；y(t) = (B + cosh(lerp(HStart, HEnd, t))) / A
// 13cm 导线端点等高时中点仅下垂 (cosh1-cosh0)/A ≈ 1.2cm（此前误把 A 当下垂量，
// 6cm 下垂扎进桌面，穿模渲染成扇形）。
function catenaryY(len, ay, by) {
  const A = 60 / Math.log10(Math.max(len * 100, 2));
  const sY = ay * A;
  const tY = by * A;
  let Hs = -1, He = 1, B;
  const acosh = (x) => Math.log(x + Math.sqrt(x * x - 1));
  if (sY > tY) {
    B = tY - Math.cosh(He);
    Hs = -acosh(Math.cosh(1) + (sY - tY));
  } else if (sY < tY) {
    B = sY - Math.cosh(Hs);
    He = acosh(Math.cosh(1) + (tY - sY));
  } else {
    B = sY - Math.cosh(Hs);
  }
  return (t) => (B + Math.cosh(Hs + (He - Hs) * t)) / A;
}

// 完整导线路径：平面路由 → Catmull-Rom 平滑（Unity 自然样条近似）→ 悬链高度
function buildWirePath(pa, pb, obstacles) {
  const wps = routeWire2D(pa.x, pa.z, pb.x, pb.z, obstacles);
  // 折线总长
  let total = 0;
  const segLens = [];
  for (let i = 1; i < wps.length; i++) {
    const l = Math.hypot(wps[i].x - wps[i - 1].x, wps[i].z - wps[i - 1].z);
    segLens.push(l);
    total += l;
  }
  // 每段插值点数，照抄 Unity：S = clamp(round(len²/0.02), 3, 10)
  const flat = [];
  const v3 = (p, y) => new THREE.Vector3(p.x, y, p.z);
  if (wps.length === 2) {
    const N = Math.max(12, Math.min(40, Math.round(total * 100)));
    for (let i = 0; i <= N; i++) flat.push({ x: wps[0].x + ((wps[1].x - wps[0].x) * i) / N, z: wps[0].z + ((wps[1].z - wps[0].z) * i) / N });
  } else {
    // Catmull-Rom 平滑折线（张点用端点复制）
    const ctrl = [wps[0], ...wps, wps[wps.length - 1]];
    for (let i = 1; i < ctrl.length - 2; i++) {
      const p0 = ctrl[i - 1], p1 = ctrl[i], p2 = ctrl[i + 1], p3 = ctrl[i + 2];
      const segLen = segLens[i - 1];
      const S = Math.max(3, Math.min(10, Math.round((segLen * segLen) / 0.02)));
      for (let n = 0; n < S; n++) {
        const t = n / S;
        const t2 = t * t, t3 = t2 * t;
        const x = 0.5 * (2 * p1.x + (-p0.x + p2.x) * t + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3);
        const z = 0.5 * (2 * p1.z + (-p0.z + p2.z) * t + (2 * p0.z - 5 * p1.z + 4 * p2.z - p3.z) * t2 + (-p0.z + 3 * p1.z - 3 * p2.z + p3.z) * t3);
        flat.push({ x, z });
      }
    }
    flat.push({ x: wps[wps.length - 1].x, z: wps[wps.length - 1].z });
  }
  // 悬链高度按全局弧长参数挂（Unity：y 与平面路由解耦，只由总长+端高差决定）
  const catY = catenaryY(total, pa.y, pb.y);
  const pts = flat.map((p, i) => v3(p, catY(i / (flat.length - 1))));
  return new THREE.CatmullRomCurve3(pts);
}

export class WireSystem {
  constructor(scene) {
    this.scene = scene;
    this.group = new THREE.Group();
    this.group.name = "wires";
    scene.add(this.group);
    this.views = new Map(); // wire data -> { mesh }
    this.tubeGeo = new THREE.CylinderGeometry(0.004, 0.004, 1, 6, 1, true);
  }

  colorOf(wire) {
    return wireColorHex(wire.colorName);
  }

  sync(wires, elementObjects) {
    // remove stale
    for (const [wire, view] of this.views) {
      if (!wires.includes(wire)) {
        this.group.remove(view.mesh);
        view.mesh.geometry.dispose();
        view.mesh.material.dispose();
        this.views.delete(wire);
      }
    }
    for (const wire of wires) {
      const a = elementObjects.get(wire.source);
      const b = elementObjects.get(wire.target);
      if (!a || !b) continue;
      const pa = pinWorld(a, wire.sourcePin);
      const pb = pinWorld(b, wire.targetPin);
      if (!pa || !pb) continue;
      // 平面障碍：除两端元件外的所有元件 AABB；检测盒外扩 8mm（导线半径
      // 0.0045 的 ~2 倍）使「贴边」也被判相交，配合角点外扩 4mm 保证绕行段
      // 与盒体留出净空（Unity 缩小碰撞盒+侧别惩罚的等效实现）
      const obstacles = [];
      for (const [id, g] of elementObjects) {
        if (id === wire.source || id === wire.target) continue;
        const size = g.userData.size || {};
        obstacles.push({
          x: g.position.x,
          z: g.position.z,
          hx: (size.x || 0.1) / 2 + 0.008,
          hz: (size.z || 0.1) / 2 + 0.008,
        });
      }
      const color = this.colorOf(wire);
      let view = this.views.get(wire);
      if (!view) {
        const curve = buildWirePath(pa, pb, obstacles);
        const geometry = new THREE.TubeGeometry(curve, 24, 0.0045, 6, false);
        const material = new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.0 });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.castShadow = true;
        mesh.userData.wire = wire;
        this.group.add(mesh);
        this.views.set(wire, { mesh });
      } else {
        const curve = buildWirePath(pa, pb, obstacles);
        view.mesh.geometry.dispose();
        view.mesh.geometry = new THREE.TubeGeometry(curve, 24, 0.0045, 6, false);
        view.mesh.material.color.setHex(color);
      }
    }
  }
}

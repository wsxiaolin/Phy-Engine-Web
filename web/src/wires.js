import * as THREE from "three";
import { WIRE_COLORS } from "./catalog.js";
import { pinWorld } from "./components.js";

export function wireColorHex(name) {
  const c = WIRE_COLORS.find((w) => w.name === name);
  return c ? c.hex : WIRE_COLORS[1].hex;
}

// 悬链线，照抄 Unity CircuitWire.Render：
//   A = 60/log10(len_cm)；y(t) = (B + cosh(lerp(HStart, HEnd, t))) / A
// 13cm 导线端点等高时中点仅下垂 (cosh1-cosh0)/A ≈ 1.2cm（此前误把 A 当下垂量，
// 6cm 下垂扎进桌面，穿模渲染成扇形）。
function buildCurve(a, b) {
  const len = a.distanceTo(b);
  const A = 60 / Math.log10(Math.max(len * 100, 2));
  const sY = a.y * A;
  const tY = b.y * A;
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
  const pts = [];
  const N = 20;
  for (let i = 0; i <= N; i++) {
    const t = i / N;
    const p = new THREE.Vector3().lerpVectors(a, b, t);
    p.y = (B + Math.cosh(Hs + (He - Hs) * t)) / A;
    pts.push(p);
  }
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
      const color = this.colorOf(wire);
      let view = this.views.get(wire);
      if (!view) {
        const curve = buildCurve(pa, pb);
        const geometry = new THREE.TubeGeometry(curve, 20, 0.0045, 6, false);
        const material = new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.0 });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.castShadow = true;
        mesh.userData.wire = wire;
        this.group.add(mesh);
        this.views.set(wire, { mesh });
      } else {
        const curve = buildCurve(pa, pb);
        view.mesh.geometry.dispose();
        view.mesh.geometry = new THREE.TubeGeometry(curve, 20, 0.0045, 6, false);
        view.mesh.material.color.setHex(color);
      }
    }
  }
}

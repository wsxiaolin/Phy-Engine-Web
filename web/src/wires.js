import * as THREE from "three";
import { WIRE_COLORS } from "./catalog.js";
import { pinWorld } from "./components.js";

export function wireColorHex(name) {
  const c = WIRE_COLORS.find((w) => w.name === name);
  return c ? c.hex : WIRE_COLORS[1].hex;
}

// Catenary sag like Unity CircuitWire.Reroute: A = 60/log10(len*100).
function buildCurve(a, b) {
  const len = a.distanceTo(b);
  const sag = Math.min(0.06, (60 / Math.log10(Math.max(len * 100, 2))) * 0.01);
  const mid = a.clone().add(b).multiplyScalar(0.5);
  mid.y -= sag;
  return new THREE.QuadraticBezierCurve3(a, mid, b);
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

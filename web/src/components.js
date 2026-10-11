import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { byId, pinsOf } from "./catalog.js";

const loader = new GLTFLoader();
const templateCache = new Map();

async function template(modelId) {
  if (templateCache.has(modelId)) return templateCache.get(modelId);
  const entry = byId(modelId);
  if (!entry) throw new Error("unknown model: " + modelId);
  const gltf = await loader.loadAsync(`/assets/components/${entry.glb}`);
  const src = gltf.scene;
  src.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
      if (o.material && o.material.map) o.material.map.colorSpace = THREE.SRGBColorSpace;
    }
  });
  templateCache.set(modelId, src);
  return src;
}

const PIN_RADIUS = 0.008;
const pinGeo = new THREE.SphereGeometry(PIN_RADIUS, 10, 8);
const pinMatIdle = new THREE.MeshBasicMaterial({ color: 0x9aa7b8, transparent: true, opacity: 0.55 });
const pinMatHot = new THREE.MeshBasicMaterial({ color: 0x2f7de1 });

// Build a placed component: GLB clone + pin anchor pick spheres + selection box.
export async function createComponent(modelId, { pickable = true } = {}) {
  const group = new THREE.Group();
  group.name = modelId;
  const src = await template(modelId);
  const clone = src.clone(true);

  // bounding box (for outline + label height)
  const box = new THREE.Box3().setFromObject(clone);
  const size = box.getSize(new THREE.Vector3());
  group.userData.size = size;

  // Recenter model so its footprint sits on the table and rotates about its centre.
  const center = box.getCenter(new THREE.Vector3());
  clone.position.x -= center.x;
  clone.position.z -= center.z;
  clone.position.y -= box.min.y;
  group.add(clone);

  const pins = pinsOf(modelId);
  const anchors = new THREE.Group();
  anchors.name = "pins";
  group.add(anchors);
  for (let i = 0; i < pins.length; i++) {
    const marker = new THREE.Mesh(pinGeo, pinMatIdle.clone());
    marker.position.set(pins[i].position[0], pins[i].position[1], pins[i].position[2]);
    marker.userData.pinIndex = i;
    marker.userData.pinName = pins[i].name;
    marker.userData.isPin = true;
    marker.visible = false; // shown on hover / wire mode
    anchors.add(marker);
  }
  group.userData.pinLocal = pins.map((p) => new THREE.Vector3(p.position[0], p.position[1], p.position[2]));
  group.userData.pinNames = pins.map((p) => p.name);
  group.userData.pickable = pickable;
  return group;
}

export function pinWorld(group, index) {
  const local = group.userData.pinLocal[index];
  if (!local) return null;
  return group.localToWorld(local.clone());
}

export function setPinsVisible(group, visible) {
  const anchors = group.getObjectByName("pins");
  if (!anchors) return;
  anchors.children.forEach((m) => {
    m.visible = visible;
  });
}

export function highlightPin(mesh, on) {
  if (!mesh) return;
  mesh.material = on ? pinMatHot : pinMatIdle;
  mesh.scale.setScalar(on ? 1.6 : 1);
}

// ---- offscreen palette thumbnails ---------------------------------------
let _thumbRig = null;
const thumbCache = new Map();

function thumbRig() {
  if (_thumbRig) return _thumbRig;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(32, 1, 0.01, 20);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x9aa3b2, 1.6));
  const key = new THREE.DirectionalLight(0xffffff, 2.4);
  key.position.set(1.4, 2.2, 1.8);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xdce8ff, 0.9);
  fill.position.set(-1.6, 1.1, -1.4);
  scene.add(fill);
  _thumbRig = { renderer, scene, cam };
  return _thumbRig;
}

export async function thumbnail(modelId, w = 124, h = 112) {
  if (thumbCache.has(modelId)) return thumbCache.get(modelId);
  const { renderer, scene, cam } = thumbRig();
  renderer.setSize(w, h, false);
  cam.aspect = w / h;
  cam.updateProjectionMatrix();
  const src = await template(modelId);
  const clone = src.clone(true);
  const box = new THREE.Box3().setFromObject(clone);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  clone.position.sub(center);
  scene.add(clone);
  const r = Math.max(size.x, size.y, size.z) || 1;
  const dist = (r / (2 * Math.tan((32 * Math.PI) / 360))) * 1.85;
  cam.position.set(dist * 0.7, dist * 0.6, dist * 0.88);
  cam.lookAt(0, 0, 0);
  renderer.render(scene, cam);
  const url = renderer.domElement.toDataURL("image/png");
  scene.remove(clone);
  thumbCache.set(modelId, url);
  return url;
}

export function pinMeshAt(group, point) {
  const anchors = group.getObjectByName("pins");
  if (!anchors) return null;
  let best = null;
  let bestD = PIN_RADIUS * 3.5;
  const p = point.clone();
  group.worldToLocal(p);
  for (const m of anchors.children) {
    const d = m.position.distanceTo(p);
    if (d < bestD) {
      bestD = d;
      best = m;
    }
  }
  return best;
}

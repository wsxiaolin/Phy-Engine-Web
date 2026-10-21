import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { byId, pinsOf } from "./catalog.js";

const loader = new GLTFLoader();
const templateCache = new Map();

async function template(modelId) {
  if (templateCache.has(modelId)) return templateCache.get(modelId);
  const entry = byId(modelId);
  if (!entry) throw new Error("unknown model: " + modelId);
  const gltf = await loader.loadAsync(`${import.meta.env.BASE_URL}assets/components/${entry.glb}`);
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

// 接线柱来源二选一（2026-10-21 起默认 GLB 网格）：
// - GLB 内置 FBX pin 网格（提取器 KEEP_PIN_MESHES=1 + 基础件.FBX Geometric
//   烘焙修复后，柱心/柱底与 prefab TRS 数值锚定，官方预览对照 PASS）——
//   Unity 真身为香蕉插头座（正极红/负极黑，见 Previews/Circuits/Resistor.png）。
// - 旧程序化柱（POST_R/POST_H）：GLB 无 pin 网格的元件兜底，视觉规格见
//   Resistor.png 量取（顶部金属帽）。两者互斥，由 glbHasPinMesh 检测切换。
const POST_R = 0.0045;
const POST_H = 0.022;
const postGeo = new THREE.CylinderGeometry(POST_R, POST_R * 1.25, POST_H, 12);
const postTipGeo = new THREE.SphereGeometry(POST_R * 0.9, 10, 8);
const postMatRed = new THREE.MeshStandardMaterial({ color: 0xc23b32, roughness: 0.5, metalness: 0.1 });
const postMatBlack = new THREE.MeshStandardMaterial({ color: 0x2c2c30, roughness: 0.5, metalness: 0.1 });
const postTipMat = new THREE.MeshStandardMaterial({ color: 0xb8bec8, roughness: 0.35, metalness: 0.85 });
const PIN_NAME_RE = /^pin/i; // 与提取器 is_pin_node 判定同源

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

  // Unity 保真：不做 recenter。prefab 根原点即桌面接触点与旋转中心
  // （Unity 里元件根节点 y=桌面高度、模型自根向上长、旋转绕根）。
  // 引线端点用 catalog 的 pin 数据（与 GLB 节点矩阵同源，tools/fix_pins.py）。
  group.add(clone);

  const pins = pinsOf(modelId);
  const anchors = new THREE.Group();
  anchors.name = "pins";
  group.add(anchors);
  // GLB 自带 FBX pin 网格时跳过程序化柱（互斥，避免双重渲染）；
  // marker 拾取球与 pinLocal（导线端点/交互）不受影响，仍按 catalog 生成。
  let glbHasPinMesh = false;
  clone.traverse((o) => {
    if (o.isMesh && PIN_NAME_RE.test(o.name || "")) glbHasPinMesh = true;
  });
  for (let i = 0; i < pins.length; i++) {
    const [px, py, pz] = pins[i].position;
    if (!glbHasPinMesh) {
      // 香蕉插头座（常驻可见）：正极红/负极黑，顶金属帽；导线端点落在柱顶
      const bodyMat = pins[i].isPositive ? postMatRed : postMatBlack;
      const post = new THREE.Mesh(postGeo, bodyMat);
      post.position.set(px, py - POST_H / 4, pz);
      post.castShadow = true;
      post.userData.pinIndex = i;
      post.userData.pinName = pins[i].name;
      post.userData.isPin = true;
      anchors.add(post);
      const tip = new THREE.Mesh(postTipGeo, postTipMat);
      tip.position.set(px, py + POST_H / 4, pz);
      tip.userData.pinIndex = i;
      tip.userData.pinName = pins[i].name;
      tip.userData.isPin = true;
      anchors.add(tip);
    }
    // 拾取球（比柱身大，hover/连线命中用）
    const marker = new THREE.Mesh(pinGeo, pinMatIdle.clone());
    marker.position.set(px, py, pz);
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
    // 金属柱常驻；仅切换拾取标记球
    if (m.geometry === pinGeo) m.visible = visible;
  });
}

export function highlightPin(mesh, on) {
  if (!mesh) return;
  if (mesh.geometry !== pinGeo) return; // 金属柱共享材质，不做换色
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

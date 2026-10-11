import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

export const TABLE_Y = 0.78; // room.glb table top height (metres, Y-up)
export const TABLE_BOUNDS = { x: 0.78, z: 0.72 }; // half extents of usable table area

export function initScene(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.88;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xdfe7f1);

  // Image-based lighting for realistic wood / metal / plastic.
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.6;

  // Unity CircuitCamera oblique45 preset: FoV 30°, pitch 50°, distance 1.4,
  // vision center = table center + (0, 0.3, -0.45).
  // cam pos = center - forward*1.4 where forward pitches 50° down toward -Z side.
  const camera = new THREE.PerspectiveCamera(30, window.innerWidth / window.innerHeight, 0.02, 100);
  camera.position.set(0, 2.15, 1.35);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, TABLE_Y + 0.3, -0.45);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.maxPolarAngle = Math.PI * 0.49;
  controls.minDistance = 0.25;
  controls.maxDistance = 3.5;
  controls.enablePan = false;
  controls.update();

  const hemi = new THREE.HemisphereLight(0xffffff, 0x9aa7b8, 0.75);
  scene.add(hemi);

  const key = new THREE.DirectionalLight(0xfff2dd, 1.05);
  key.position.set(1.6, 3.8, 1.8);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  const s = 4.5;
  key.shadow.camera.left = -s;
  key.shadow.camera.right = s;
  key.shadow.camera.top = s;
  key.shadow.camera.bottom = -s;
  key.shadow.camera.near = 0.5;
  key.shadow.camera.far = 12;
  key.shadow.bias = -0.0005;
  scene.add(key);

  const fill = new THREE.DirectionalLight(0xdce8ff, 0.35);
  fill.position.set(-2.2, 2.4, -1.6);
  scene.add(fill);

  const roomGroup = new THREE.Group();
  scene.add(roomGroup);

  return { renderer, scene, camera, controls, roomGroup };
}


export async function loadRoom(roomGroup) {
  const loader = new GLTFLoader();
  const gltf = await loader.loadAsync("/assets/room.glb");
  const root = gltf.scene;
  root.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
      if (o.material) {
        o.material.side = THREE.FrontSide;
        if (o.material.map) o.material.map.colorSpace = THREE.SRGBColorSpace;
      }
    }
  });
  roomGroup.add(root);
  return root;
}

// Ray → table-top plane intersection (for drag placement).
export function tablePlane() {
  return new THREE.Plane(new THREE.Vector3(0, 1, 0), -TABLE_Y);
}

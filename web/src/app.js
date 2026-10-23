import * as THREE from "three";
import { initScene, loadRoom, TABLE_Y, tablePlane } from "./scene.js";
import { createComponent, pinWorld, setPinsVisible, highlightPin } from "./components.js";
import { WireSystem } from "./wires.js";
import { UI } from "./ui.js";
import { Experiment, defaultProps } from "./state.js";
import { initEngine, Engine } from "./engine.js";
import { byId, isSupported, WIRE_COLORS } from "./catalog.js";
import { METER_MODELS, expandMeters, meterStatistics, pinWiredOf, pointerAngle } from "./meters.js";

const SNAP = 0; // Unity has no grid snapping; free continuous placement.
const TABLE_HALF_X = 0.74;
const TABLE_HALF_Z = 0.7;

const snap = (v) => (SNAP > 0 ? Math.round(v / SNAP) * SNAP : v);
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export class App {
  constructor(canvas) {
    this.canvas = canvas;
    this.world = initScene(canvas);
    this.ui = new UI();
    this.experiment = new Experiment();
    this.engine = new Engine();
    this.rails = { mode: "idle", selection: null, placing: null, dragging: null, pendingWire: null };
    this.elementObjects = new Map();
    this.wireSystem = new WireSystem(this.world.scene);

    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.plane = tablePlane();
    this.hover = null;
    this.wireColor = WIRE_COLORS[0].name;
    this.running = true;

    this._selectBox = new THREE.BoxHelper(new THREE.Object3D(), 0x2f7de1);
    this._selectBox.visible = false;
    this.world.scene.add(this._selectBox);

    this._wirePreview = null;
    this._simTimer = null;
  }

  async init() {
    const t0 = performance.now();
    this.ui.buildPalette((item) => this.beginPlacing(item));
    this.ui.buildWireBar((name) => {
      this.wireColor = name;
      this.ui.toast(`已选中 ${name}。`); // Unity DialogWires 同款提示
    }, this.wireColor);
    this.bindUI();
    this.bindPointer();
    window.addEventListener("resize", () => this.onResize());
    await loadRoom(this.world.roomGroup);
    await initEngine();
    this.firstFrameMs = performance.now() - t0;
    this.ui.setPerf(`首屏 ${this.firstFrameMs.toFixed(0)} ms`);
    this.loop();
  }

  bindUI() {
    const file = document.createElement("input");
    file.type = "file";
    file.accept = ".plsave,.sav,.json";
    file.addEventListener("change", () => {
      const f = file.files[0];
      if (!f) return;
      f.text().then((txt) => this.loadJson(JSON.parse(txt)));
    });

    const add = document.getElementById("btn-add");
    add.onclick = () => {
      this.ui.togglePalette();
      add.classList.toggle("active", !this.ui._paletteOpen);
    };

    const pause = document.getElementById("btn-pause");
    pause.onclick = () => {
      if (!this.hasSimulated) {
        // First press acts as "run": run a full analyze and show feedback.
        this.hasSimulated = true;
        this.running = true;
        this.simulate(true);
        pause.classList.add("active");
        this.ui.toast("仿真已启动 · 再按暂停");
        return;
      }
      this.running = !this.running;
      pause.classList.toggle("active", !this.running);
      this.ui.toast(this.running ? "已继续" : "已暂停");
    };

    this.speeds = ["1s/s", "2s/s", "0.5s/s", "0.2s/s"];
    this.speedIdx = 0;
    const speed = document.getElementById("btn-speed");
    speed.onclick = () => {
      this.speedIdx = (this.speedIdx + 1) % this.speeds.length;
      speed.textContent = this.speeds[this.speedIdx];
    };

    const more = document.getElementById("btn-more");
    const menu = document.getElementById("more-menu");
    more.onclick = (e) => {
      e.stopPropagation();
      menu.classList.toggle("hidden");
    };
    document.addEventListener("pointerdown", (e) => {
      if (!menu.classList.contains("hidden") && !menu.contains(e.target) && e.target !== more) menu.classList.add("hidden");
    });
    menu.querySelectorAll("button").forEach((b) => {
      b.onclick = () => {
        menu.classList.add("hidden");
        if (b.dataset.act === "new") this.reset();
        else if (b.dataset.act === "save") this.save();
        else if (b.dataset.act === "load") file.click();
      };
    });

    document.getElementById("btn-back").onclick = () => this.ui.toast("返回");
    document.getElementById("btn-ar").onclick = () => this.ui.toast("AR 预览暂未开放");
    document.getElementById("btn-wire").onclick = () => this.ui.toggleWireBar();

    this.bindJoystick();
  }

  bindJoystick() {
    const stick = document.getElementById("joystick");
    const knob = document.getElementById("joystick-knob");
    const R = 28;
    let active = false;
    const move = (e) => {
      const r = stick.getBoundingClientRect();
      let dx = e.clientX - (r.left + r.width / 2);
      let dy = e.clientY - (r.top + r.height / 2);
      const len = Math.hypot(dx, dy);
      if (len > R) {
        dx = (dx / len) * R;
        dy = (dy / len) * R;
      }
      knob.style.transform = `translate(${dx}px, ${dy}px)`;
      this._joy = { x: dx / R, y: dy / R };
    };
    stick.addEventListener("pointerdown", (e) => {
      active = true;
      stick.setPointerCapture(e.pointerId);
      move(e);
    });
    stick.addEventListener("pointermove", (e) => {
      if (active) move(e);
    });
    const end = () => {
      active = false;
      this._joy = null;
      knob.style.transform = "";
    };
    stick.addEventListener("pointerup", end);
    stick.addEventListener("pointercancel", end);

    // Delete/Backspace：删选中导线或元件（Unity CircuitMode: KeyCode.Delete）
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Delete" && e.key !== "Backspace") return;
      const tag = document.activeElement?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (this.deleteSelectedWire()) {
        e.preventDefault();
        return;
      }
      if (this.rails.selection) {
        this.deleteElement(this.rails.selection);
        e.preventDefault();
      }
    });
  }

  applyJoystick() {
    const j = this._joy;
    if (!j) return;
    const { camera, controls } = this.world;
    const offset = camera.position.clone().sub(controls.target);
    const sph = new THREE.Spherical().setFromVector3(offset);
    sph.theta -= j.x * 0.045;
    sph.phi = Math.max(0.2, Math.min(Math.PI * 0.46, sph.phi - j.y * 0.035));
    offset.setFromSpherical(sph);
    camera.position.copy(controls.target).add(offset);
    camera.lookAt(controls.target);
  }

  bindPointer() {
    const el = this.canvas;
    this._activePtrs = new Set(); // 触摸活动指针（双指缩放手势判定）
    el.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "mouse") {
        this.onPointerDown(e);
        return;
      }
      this._activePtrs.add(e.pointerId);
      // 双指 = 捏合缩放（OrbitControls dolly）：撤销单指拖拽，控制权交还相机
      if (this._activePtrs.size >= 2) {
        this.rails.dragging = null;
        this.world.controls.enabled = true;
        return;
      }
      const handled = this.onPointerDown(e);
      // 单指命中交互（拖元件/选 pin/接线）时暂禁相机旋转，避免拖拽带动视角
      if (handled) this.world.controls.enabled = false;
    });
    const release = (e) => {
      this._activePtrs.delete(e.pointerId);
      if (this._activePtrs.size === 0) this.world.controls.enabled = true;
      this.rails.dragging = null;
    };
    el.addEventListener("pointermove", (e) => this.onPointerMove(e));
    el.addEventListener("pointerup", release);
    el.addEventListener("pointercancel", release);
    el.addEventListener("contextmenu", (e) => e.preventDefault());
    // Unity: scroll wheel rotates the hovered/selected component in 30° steps.
    // capture 阶段拦截，独占旋转语义（空白处滚轮仍走 OrbitControls 缩放）
    document.addEventListener(
      "wheel",
      (e) => {
        if (!this.canvas.contains(e.target)) return;
        if (this.hover || this.rails.selection) {
          e.preventDefault();
          e.stopImmediatePropagation();
          const id = this.hover?.userData.elementId || this.rails.selection;
          const step = Math.sign(e.deltaY) * (Math.PI / 6); // 30°
          this.rotateBy(id, step);
        }
      },
      { passive: false, capture: true },
    );
  }

  // ---- pointer helpers -------------------------------------------------

  setPointer(e) {
    const r = this.canvas.getBoundingClientRect();
    this.pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    this.pointer.y = -((e.clientY - r.top) / r.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.world.camera);
  }

  planePoint() {
    const p = new THREE.Vector3();
    return this.raycaster.ray.intersectPlane(this.plane, p) ? p : null;
  }

  pick() {
    const objects = [...this.elementObjects.values()];
    const hits = this.raycaster.intersectObjects(objects, true);
    for (const h of hits) {
      let o = h.object;
      while (o && !objects.includes(o)) o = o.parent;
      if (o) return { group: o, hit: h, pin: h.object.userData.isPin ? h.object : null };
    }
    return null;
  }

  // Screen-space nearest-pin test, mirroring Unity WireManager.TryLocatePin:
  // project every pin to screen pixels, take the closest within threshold.
  pickPin(clientX, clientY) {
    const r = this.canvas.getBoundingClientRect();
    const w = this.world.renderer.domElement.clientWidth;
    const h = this.world.renderer.domElement.clientHeight;
    const fovCoef = 0.15 + 0.85 * (1 / this.world.camera.projectionMatrix.elements[5]);
    const threshold = 26 * fovCoef; // generous touch target (Unity: DPI/13 ≈ 12px)
    let best = null;
    let bestD = threshold;
    const v = new THREE.Vector3();
    for (const g of this.elementObjects.values()) {
      const anchors = g.getObjectByName("pins");
      if (!anchors) continue;
      for (const m of anchors.children) {
        v.copy(m.position);
        g.localToWorld(v);
        v.project(this.world.camera);
        if (v.z >= 1) continue; // behind camera
        const sx = r.left + ((v.x + 1) / 2) * w;
        const sy = r.top + ((-v.y + 1) / 2) * h;
        const d = Math.hypot(sx - clientX, sy - clientY);
        if (d < bestD) {
          bestD = d;
          best = { group: g, pin: m, screenDist: d };
        }
      }
    }
    return best;
  }

  // ---- interaction -----------------------------------------------------

  // 返回 true = 本次按下命中交互（拖元件/pin/接线/放置），触摸端据此暂禁相机旋转
  onPointerDown(e) {
    if (e.button === 2) {
      // right-click: rotate hovered/selected
      this.setPointer(e);
      const p = this.pick();
      const g = p?.group || this.rails.selection;
      if (g) this.rotate(typeof g === "object" ? g.userData.elementId : g);
      return false;
    }
    this.setPointer(e);

    // Wiring: clicking a component that is already selected routes to pin select
    // (Unity: selected component click -> TrySelectPin).
    const pinHit = this.pickPin(e.clientX, e.clientY);
    if (this.rails.pendingWire && pinHit) {
      this.handlePin(pinHit.group, pinHit.pin.userData.pinIndex);
      return true;
    }

    const p = this.pick();
    if (p) {
      const id = p.group.userData.elementId;
      if (this.rails.selection === id) {
        // 已选中：开关类二次点击=拨动开关（Unity: 开关面板拨杆）
        if (this.toggleInteractive(id)) return true;
        if (pinHit && pinHit.group.userData.elementId === id) {
          this.handlePin(p.group, pinHit.pin.userData.pinIndex);
          return true;
        }
      }
      this.select(p.group);
      this.rails.dragging = { id, moved: false };
      const el = this.experiment.getElement(id);
      this._dragStart = { x: el.position.x, z: el.position.z, px: e.clientX, py: e.clientY };
      return true;
    }

    // 导线点选（Unity: 点导线选中，Delete 删除）
    if (!this.rails.pendingWire) {
      const wHits = this.raycaster.intersectObjects(this.wireSystem.group.children, false);
      if (wHits.length) {
        const view = this.wireSystem.views.get(wHits[0].object.userData.wire);
        if (view) {
          this.selectWire(view);
          return true;
        }
      }
    }

    if (this.rails.placing) {
      const pt = this.planePoint();
      if (pt) this.commitPlacing(pt);
      return true;
    }
    this.selectWire(null);
    this.select(null);
    return false;
  }

  onPointerMove(e) {
    this.setPointer(e);
    if (this.rails.dragging) {
      const el = this.experiment.getElement(this.rails.dragging.id);
      const pt = this.planePoint();
      if (el && pt) {
        if (Math.abs(e.clientX - this._dragStart.px) + Math.abs(e.clientY - this._dragStart.py) > 3)
          this.rails.dragging.moved = true;
        const x = clamp(snap(pt.x), -TABLE_HALF_X, TABLE_HALF_X);
        const z = clamp(snap(pt.z), -TABLE_HALF_Z, TABLE_HALF_Z);
        el.position.x = x;
        el.position.z = z;
        const g = this.elementObjects.get(el.id);
        g.position.set(x, TABLE_Y, z);
        this.syncWires();
      }
      return;
    }
    if (this.rails.placing) {
      const pt = this.planePoint();
      if (pt) {
        this.rails.placing.ghost.position.set(
          clamp(snap(pt.x), -TABLE_HALF_X, TABLE_HALF_X),
          TABLE_Y,
          clamp(snap(pt.z), -TABLE_HALF_Z, TABLE_HALF_Z),
        );
      }
      return;
    }

    const p = this.pick();
    const ng = p ? p.group : null;
    if (ng !== this.hover) {
      if (this.hover) setPinsVisible(this.hover, this.hover === this.rails.selection);
      this.hover = ng;
      if (this.hover) setPinsVisible(this.hover, true);
    }
    if (this.rails.pendingWire) this.updateWirePreview();
  }

  // ---- placement -------------------------------------------------------

  beginPlacing(item) {
    this.select(null);
    const ghost = new THREE.Group();
    const box = new THREE.Mesh(
      new THREE.BoxGeometry(0.13, 0.05, 0.13),
      new THREE.MeshBasicMaterial({ color: 0x2f7de1, transparent: true, opacity: 0.35 }),
    );
    box.position.y = 0.025;
    ghost.add(box);
    ghost.position.set(0, TABLE_Y, 0);
    this.world.scene.add(ghost);
    this.rails.placing = { item, ghost };
    this.ui.toast(`放置：${item.FriendlyName || item.ModelID}（点击桌面确认，Esc 取消）`);
  }

  async commitPlacing(pt) {
    const { item, ghost } = this.rails.placing;
    this.world.scene.remove(ghost);
    this.rails.placing = null;
    const pos = {
      x: clamp(snap(pt.x), -TABLE_HALF_X, TABLE_HALF_X),
      y: TABLE_Y,
      z: clamp(snap(pt.z), -TABLE_HALF_Z, TABLE_HALF_Z),
    };
    const el = this.experiment.addElement({
      modelId: item.ModelID,
      label: item.FriendlyName || item.ModelID,
      position: pos,
      properties: defaultProps(item.ModelID),
    });
    await this.instantiate(el);
    this.select(el.id);
    this.scheduleSimulate();
  }

  async instantiate(el) {
    const group = await createComponent(el.modelId);
    group.userData.elementId = el.id;
    group.position.set(el.position.x, el.position.y, el.position.z);
    group.rotation.y = el.rotY || 0;
    this.world.scene.add(group);
    this.elementObjects.set(el.id, group);
    this.syncPole(el, group);
    this.syncLED(el, group);
    return group;
  }

  // 开关拨杆姿态（GLTFLoader 后节点名为 "Pole"，原始 rotation.x=0.79 即
  // 翘起断开位；闭合压平到 0。Unity 端由 Animator 驱动，此处按属性直达）
  syncPole(el, group) {
    const g = group || this.elementObjects.get(el.id);
    if (!g) return;
    const pole = g.getObjectByName("Pole");
    if (!pole) return;
    const on = Number(el.properties["开关"] ?? 0) !== 0;
    pole.rotation.x = on ? 0 : 0.79;
    g.userData.pole = pole;
  }

  // M8 电表渲染循环（Unity Render/RenderPointer 一比一）：
  // 指针节点 = prefab MeterPointer 序列化目标 = 内层「指针」（挂 mesh、无 children；
  // 外层同名节点是建模姿态父层，动它会连 21.72 缩放一起歪）。Unity RenderPointer
  // 用 localEulerAngles=(0,Ratio,0) 整覆盖本地旋转——GLB 提取语义 q 原样不共轭
  // （镜像统一交给顶层 X_MIRROR），故 three 侧同分量直设 rotation=(0,Ratio,0)。
  // 语义三分支照抄 Unity Render()：未连接→0 值归零；已连接未烧毁→刻度；
  // 烧毁→不调用（指针冻结在末位，pointerAngle 返回 null 表达）。
  // 电能表无指针：Unity SyncStatistics 每帧 Properties["示数"] += 功率×DeltaTime/3600，
  // 此处以渲染步长 dt 等价累积（Unity sim tick 与帧同步）。
  updateMeters(dt) {
    for (const el of this.experiment.elements) {
      if (!METER_MODELS.has(el.modelId)) continue;
      const g = this.elementObjects.get(el.id);
      if (!g) continue;
      if (el.modelId === "Electricity Meter") {
        const p = Number((el.statistics || {})["功率"]) || 0;
        if (this.running && !el.broken && p !== 0) {
          const prev = Number(el.properties?.["示数"]) || 0;
          el.properties["示数"] = +(prev + (p * dt) / 3600).toFixed(6);
          el.statistics = { ...(el.statistics || {}), 示数: el.properties["示数"] };
        }
        continue;
      }
      let needle = g.userData.meterNeedle;
      if (needle === undefined) {
        needle = null;
        // 节点名「指针」：GLB 内外层同名（外层姿态组 + 内层 mesh），GLTFLoader
        // 加载去重会把内层改名「指针_1」（空格/重名 sanitize），正则兼容两种。
        g.traverse((o) => {
          if (needle || !/^指针(_\d+)?$/.test(o.name || "")) return;
          if (o.isMesh && (o.children || []).length === 0) needle = o;
        });
        g.userData.meterNeedle = needle;
      }
      if (needle) {
        const a = pointerAngle(el.modelId, el.statistics, el.broken);
        if (a !== null) needle.rotation.set(0, a, 0);
      }
    }
  }

  // LED 指示灯运行时着色（Unity LEDRenderer.Render 复刻）：
  // Logic Input: LEDGreen.Render(开关)——开关=1 绿光亮；Logic Output:
  // LEDRed.Render(状态)——状态 H 红光亮。LightColor 取自 prefab 序列化值
  // （绿 0.122/0.490/0，红 0.8/0.133/0）。OFF: 主体贴 LightColor 无自发光；
  // ON: _Illumin≤0.75 自发光 + 光晕点光（intensity=Luminosity*2）。
  syncLED(el, group) {
    const g = group || this.elementObjects.get(el.id);
    if (!g || !/Logic (Input|Output)/.test(el.modelId)) return;
    const input = /Logic Input/.test(el.modelId);
    const color = new THREE.Color(
      ...(input ? [0.12156863, 0.49019608, 0] : [0.8, 0.13333334, 0]),
    );
    const on = input
      ? Number(el.properties["开关"] ?? 0) !== 0
      : !!((el.statistics || {})["状态"]);
    const mainNode = g.getObjectByName(input ? "绿光" : "红光");
    const baseNode = g.getObjectByName("Helix001");
    const meshes = (node) => {
      if (!node) return [];
      const out = node.isMesh ? [node] : [];
      node.traverse((o) => o.isMesh && out.push(o));
      return out;
    };
    // 材质一次性克隆，避免跨元件实例共享（MaterialPropertyBlock 语义）
    for (const mesh of meshes(mainNode).concat(meshes(baseNode))) {
      if (mesh.userData.ledOwned) continue;
      mesh.material = Array.isArray(mesh.material)
        ? mesh.material.map((m) => m.clone())
        : mesh.material.clone();
      mesh.userData.ledOwned = true;
    }
    for (const mesh of meshes(baseNode)) {
      // BaseRenderer._Color = LightColor（底座常亮着色）
      for (const m of [].concat(mesh.material)) m.color?.copy(color);
    }
    for (const mesh of meshes(mainNode)) {
      for (const m of [].concat(mesh.material)) {
        m.color?.copy(color);
        if (m.emissive) {
          m.emissive.copy(color);
          m.emissiveIntensity = on ? 0.75 : 0;
        }
      }
    }
  // Logic Input 按钮互切（Unity LogicInput.Render: SwitchOn/SwitchOff SetActive）
    if (input) {
      const onBtn = g.getObjectByName("按钮-开");
      const offBtn = g.getObjectByName("按钮-关");
      if (onBtn) onBtn.visible = on;
      if (offBtn) offBtn.visible = !on;
    }
    // LightHalo 光晕（Luminosity=1 → intensity 2；m_Range=0.05，
    // 位置=GLB「Point Light」节点世界位，即 Unity LightHalo 局部 (5,0,0)）
    let halo = g.userData.ledHalo;
    if (on) {
      if (!halo) {
        halo = new THREE.PointLight(color.clone(), 2, 0.05, 2);
        g.userData.ledHalo = halo;
        g.add(halo);
      }
      const src = g.getObjectByName("Point Light") || mainNode;
      if (src) {
        const v = new THREE.Vector3();
        src.getWorldPosition(v);
        g.worldToLocal(v);
        halo.position.copy(v);
      }
      halo.color.copy(color);
      halo.intensity = 2;
    } else if (halo) {
      halo.intensity = 0;
    }
  }

  // Programmatic placement (also used by tests).
  async addPart(modelId, x, z, properties) {
    const item = byId(modelId);
    const el = this.experiment.addElement({
      modelId,
      label: item?.FriendlyName || modelId,
      position: { x, y: TABLE_Y, z },
      properties: properties || defaultProps(modelId),
    });
    await this.instantiate(el);
    return el;
  }

  // ---- selection / edit -----------------------------------------------

  select(target) {
    const id = target && typeof target === "object" ? target.userData.elementId : target;
    this.rails.selection = id;
    if (id) this.selectWire(null); // 选中元件时清除导线高亮
    for (const [eid, g] of this.elementObjects) setPinsVisible(g, eid === id || g === this.hover);
    if (!id) {
      this._selectBox.visible = false;
      this.ui.hideInspector();
      return;
    }
    const g = this.elementObjects.get(id);
    const el = this.experiment.getElement(id);
    if (!g || !el) return;
    this._selectBox.setFromObject(g);
    this._selectBox.visible = true;
    this.showInspector(el);
  }

  // ---- wire selection (Unity: 点导线选中，Delete 删除) --------------------

  selectWire(view) {
    if (this.rails.selWire === view) return;
    if (this.rails.selWire?.mesh) {
      this.rails.selWire.mesh.material.emissive?.setHex(0x000000);
    }
    this.rails.selWire = view;
    if (view?.mesh) {
      view.mesh.material.emissive?.setHex(0x303030);
      this.select(null);
      this.ui.toast(`已选中导线 · ${view.mesh.userData.wire?.colorName ?? ""}（Delete 删除）`);
    }
  }

  deleteSelectedWire() {
    const view = this.rails.selWire;
    if (!view) return false;
    const wire = view.wire ?? view.mesh?.userData.wire;
    this.experiment.removeWire(wire);
    this.selectWire(null);
    this.syncWires();
    this.scheduleSimulate();
    this.ui.toast("已删除导线");
    return true;
  }

  // 可交互元件：开关类点击本体切换（Unity: 开关面板拨杆）
  toggleInteractive(id) {
    const el = this.experiment.getElement(id);
    if (!el) return false;
    if (/Switch|Logic Input/.test(el.modelId)) {
      const cur = Number(el.properties["开关"] ?? 0);
      el.properties["开关"] = cur ? 0 : 1;
      this.syncPole(el);
      this.syncLED(el);
      this.ui.toast(`${el.label}：${el.properties["开关"] ? "闭合" : "断开"}`);
      this.scheduleSimulate();
      this.showInspector(el);
      return true;
    }
    return false;
  }

  showInspector(el) {
    const rows = [];
    const supported = isSupported(el.modelId);
    for (const [k, v] of Object.entries(el.properties)) {
      rows.push({
        label: k,
        value: v,
        onChange: (val) => {
          el.properties[k] = Number.isNaN(Number(val)) ? val : Number(val);
          if (k === "开关") { this.syncPole(el); this.syncLED(el); }
          this.scheduleSimulate();
        },
      });
    }
    if (el.statistics && Object.keys(el.statistics).length) {
      const parts = Object.entries(el.statistics)
        .map(([k, v]) => `${k} ${Number(v).toFixed(3)}`)
        .join("  ");
      rows.push({ label: "读数", value: parts, type: "stat" });
    }
    if (!supported) rows.push({ label: "提示", value: "引擎暂不支持，仅摆放", type: "stat" });
    this.ui.showInspector(
      el.label,
      rows,
      () => this.rotate(el.id),
      () => this.deleteElement(el.id),
    );
  }

  rotateBy(id, delta) {
    const el = this.experiment.getElement(id);
    if (!el) return;
    el.rotY = (el.rotY || 0) + delta;
    const g = this.elementObjects.get(id);
    if (g) g.rotation.y = el.rotY;
    if (this.rails.selection === id) this._selectBox.setFromObject(g);
    this.syncWires();
    this.scheduleSimulate();
  }

  rotate(id) {
    this.rotateBy(id, Math.PI / 2);
  }

  deleteElement(id) {
    const g = this.elementObjects.get(id);
    if (g) {
      this.world.scene.remove(g);
      g.traverse((o) => {
        if (o.isMesh && o.geometry && o.geometry.__component) o.geometry.dispose();
      });
    }
    this.elementObjects.delete(id);
    this.experiment.removeElement(id);
    if (this.rails.selection === id) this.select(null);
    this.syncWires();
    this.scheduleSimulate();
  }

  reset() {
    for (const id of [...this.elementObjects.keys()]) this.deleteElement(id);
    this.experiment.clear();
    this.select(null);
    this.hasSimulated = false;
    document.getElementById("btn-pause")?.classList.remove("active");
    this.ui.toast("已清空");
  }

  // ---- wiring ----------------------------------------------------------

  handlePin(group, pinIndex) {
    const id = group.userData.elementId;
    const pending = this.rails.pendingWire;
    if (!pending) {
      this.rails.pendingWire = { id, pinIndex };
      const mesh = group.getObjectByName("pins").children[pinIndex];
      highlightPin(mesh, true);
      mesh.userData.hot = true;
      this.ui.showWireBar();
      return;
    }
    if (pending.id === id && pending.pinIndex === pinIndex) {
      this.cancelWire();
      return;
    }
    // Unity semantics: creating a wire between already-connected pins removes it.
    const existing = this.experiment.wires.find(
      (w) =>
        (w.source === pending.id && w.sourcePin === pending.pinIndex && w.target === id && w.targetPin === pinIndex) ||
        (w.source === id && w.sourcePin === pinIndex && w.target === pending.id && w.targetPin === pending.pinIndex),
    );
    if (existing) {
      this.experiment.removeWire(existing);
      this.clearWirePreview();
      this.rails.pendingWire = null;
      this.syncWires();
      this.scheduleSimulate();
      this.ui.toast("已移除导线");
      return;
    }
    const w = this.experiment.addWire(pending.id, pending.pinIndex, id, pinIndex, this.wireColor);
    this.clearWirePreview();
    // clear highlight of pending pin
    const pgrp = this.elementObjects.get(pending.id);
    if (pgrp) {
      const m = pgrp.getObjectByName("pins").children[pending.pinIndex];
      if (m) {
        highlightPin(m, false);
        m.userData.hot = false;
      }
    }
    this.rails.pendingWire = null;
    if (w) {
      this.syncWires();
      this.scheduleSimulate();
    }
  }

  cancelWire() {
    const pending = this.rails.pendingWire;
    if (pending) {
      const pgrp = this.elementObjects.get(pending.id);
      if (pgrp) {
        const m = pgrp.getObjectByName("pins").children[pending.pinIndex];
        if (m) {
          highlightPin(m, false);
          m.userData.hot = false;
        }
      }
    }
    this.rails.pendingWire = null;
    this.clearWirePreview();
  }

  updateWirePreview() {
    const pending = this.rails.pendingWire;
    if (!pending) return;
    const g = this.elementObjects.get(pending.id);
    if (!g) return;
    const a = pinWorld(g, pending.pinIndex);
    const pt = this.planePoint() || a;
    if (!this._wirePreview) {
      const geo = new THREE.BufferGeometry().setFromPoints([a, pt]);
      const mat = new THREE.LineBasicMaterial({ color: 0x2f7de1 });
      this._wirePreview = new THREE.Line(geo, mat);
      this.world.scene.add(this._wirePreview);
    }
    this._wirePreview.geometry.setFromPoints([a, pt]);
  }

  clearWirePreview() {
    if (this._wirePreview) {
      this.world.scene.remove(this._wirePreview);
      this._wirePreview.geometry.dispose();
      this._wirePreview.material.dispose();
      this._wirePreview = null;
    }
    this.ui.hideWireBar();
  }

  syncWires() {
    this.wireSystem.sync(this.experiment.wires, this.elementObjects);
  }

  // ---- simulation ------------------------------------------------------

  scheduleSimulate() {
    clearTimeout(this._simTimer);
    this._simTimer = setTimeout(() => this.simulate(false), 120);
  }

  simulate(verbose) {
    this.hasSimulated = true;
    const supportedEls = this.experiment.elements.filter((e) => isSupported(e.modelId));
    const ids = new Set(supportedEls.map((e) => e.id));
    let subWires = this.experiment.wires.filter((w) => ids.has(w.source) && ids.has(w.target));
    // 只送进「有连线」的元件：悬空元件不参与求解（Unity 同语义；孤立模型
    // 会让引擎 analyze 失败）
    const connected = new Set();
    for (const w of subWires) {
      connected.add(w.source);
      connected.add(w.target);
    }
    const connectedEls = supportedEls.filter((e) => connected.has(e.id));
    const sub = new Experiment();
    sub.elements = connectedEls.map((e) => ({ ...e }));
    sub.wires = subWires.map((w) => ({ ...w })); // 展开会改写端点，必须副本
    if (!sub.elements.length) {
      this.engine.destroy();
      if (verbose) this.ui.toast("没有可仿真的元件");
      return;
    }
    // M8 电表展开：引擎无电表原生模型，照 Unity BuildElements 换成 Resistor
    // 子网络（外部导线端点同步改写到子电阻 pin）。电表本体不进引擎 payload。
    const meterInfo = expandMeters(sub.elements, sub.wires);
    sub.elements = meterInfo.elements;
    sub.wires = meterInfo.wires;
    // 引擎 build_netlist_from_wires 不做自动接地：无参考地的环路 MNA 奇异，
    // analyze 必失败（Unity 自己的求解器无此限制）。在发给引擎的 payload 里
    // 注入一个幽灵 Ground Component（只影响仿真，不进用户文档/存档）：
    // 优先接第一块电池的负极（PL Pin 2 = 索引 1），无电池则接首个元件 pin0。
    // 用户自己放了接地的则不注入。
    const hasUserGround = sub.elements.some((e) => e.modelId === "Ground Component");
    if (!hasUserGround) {
      const bat = sub.elements.find((e) => e.modelId === "Battery Source");
      const host = bat || sub.elements[0];
      const hostPin = bat ? 1 : 0;
      const g = {
        id: "__ground__",
        modelId: "Ground Component",
        label: "Ground",
        position: { x: 0, y: -10, z: 0 },
        rotY: 0,
        properties: {},
        statistics: {},
        broken: false,
      };
      sub.elements.push(g);
      sub.wires.push({ source: "__ground__", sourcePin: 0, target: host.id, targetPin: hostPin, colorName: "黑色导线" });
    }
    const t0 = performance.now();
    try {
      this.engine.load(JSON.stringify(sub.toPlsave()));
      this.engine.build();
      this.engine.analyze(0);
      this.engine.digitalClk();
      this.engine.writeBack();
      const dt = performance.now() - t0;
      const root = JSON.parse(this.engine.dump(0));
      const status = JSON.parse((root.Experiment || root).StatusSave);
      const byIdMap = new Map(this.experiment.elements.map((e) => [e.id, e]));
      for (const e of this.experiment.elements) e.statistics = {};
      // 电表子电阻压降收集（id 形如 owner::R1）
      const subU = new Map();
      for (const e of status.Elements) {
        const id = e.Identifier;
        if (typeof id === "string" && id.includes("::")) {
          const idx = id.lastIndexOf("::");
          const owner = id.slice(0, idx);
          if (!subU.has(owner)) subU.set(owner, {});
          subU.get(owner)[id.slice(idx + 2)] = Number((e.Statistics || {}).电压) || 0;
        }
      }
      for (const e of status.Elements) {
        const el = byIdMap.get(e.Identifier);
        if (el) {
          el.statistics = e.Statistics || {};
          // 引擎 write_back 只回填 MNA 支路电流（V源/电感），无源元件电流恒 0。
          // 电阻按欧姆定律本地补算，Unity 端显示语义一致（I=U/R, P=U²/R）。
          if (el.modelId === "Resistor" && Number.isFinite(el.statistics.电压)) {
            const u = el.statistics.电压;
            const r = Number(el.properties?.电阻) || 0;
            if (r > 0) {
              el.statistics.电流 = +(u / r).toFixed(6);
              el.statistics.功率 = +((u * u) / r).toFixed(6);
            }
          }
        }
      }
      // 电表读数：Unity SyncStatistics 一比一（刻度/名义量程/烧毁）
      for (const el of this.experiment.elements) {
        if (!METER_MODELS.has(el.modelId)) continue;
        const U = subU.get(el.id) || {};
        const pinWired = pinWiredOf(this.experiment.wires, el.id);
        const r = meterStatistics(el, U, pinWired, 0);
        if (!r) continue;
        el.statistics = r.statistics;
        if (r.broken && !el.broken) {
          el.broken = true;
          this.ui.toast(`${el.label} 超量程烧毁（Unity 同判定）`);
        }
      }
      this.ui.setPerf(`首屏 ${this.firstFrameMs?.toFixed(0) || "-"} ms · analyze ${dt.toFixed(1)} ms`);
      if (this.rails.selection) this.showInspector(this.experiment.getElement(this.rails.selection));
      if (verbose) this.ui.toast(`仿真完成（${dt.toFixed(1)} ms）`);
    } catch (err) {
      this.ui.toast("仿真失败：" + (err.message || err) + "（检查电路是否闭合、是否接地）");
      this.lastSimError = err.message || String(err);
    }
  }

  // ---- persistence -----------------------------------------------------

  save() {
    const blob = new Blob([JSON.stringify(this.experiment.toPlsave(), null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "circuit.plsave";
    a.click();
    URL.revokeObjectURL(a.href);
    this.ui.toast("已导出 circuit.plsave");
  }

  async loadJson(root) {
    this.reset();
    const exp = Experiment.fromPlsave(root);
    this.experiment = exp;
    for (const el of exp.elements) await this.instantiate(el);
    this.syncWires();
    this.simulate(false);
    this.ui.toast(`已加载 ${exp.elements.length} 个元件`);
  }

  // ---- loop ------------------------------------------------------------

  onResize() {
    const { camera, renderer } = this.world;
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  }

  updateLabels() {
    // Unity GetLabel/CombineLabel 规则：有效数字+单位符号、零值省略、逗号合并
    const fmt = (val, unit) => {
      const v = Number(val);
      if (!Number.isFinite(v) || v === 0) return "";
      const abs = Math.abs(v);
      const num = abs >= 100 ? v.toFixed(0) : abs >= 10 ? v.toFixed(1) : v.toFixed(2);
      return `${num}${unit}`;
    };
    const entries = [];
    for (const el of this.experiment.elements) {
      const g = this.elementObjects.get(el.id);
      if (!g) continue;
      this.syncLED(el, g);
      const parts = [];
      const st = el.statistics || {};
      if (METER_MODELS.has(el.modelId)) {
        // Unity RenderLabel 一比一：安培计/伏特计显示名义量程（如 0.6A / 3V），
        // 灵敏电流计/微安表/电能表无世界标签（base 虚方法返回 ""）。
        if (el.modelId === "Simple Ammeter" || el.modelId === "Simple Voltmeter") {
          const nominal = st["名义量程"] ?? el.properties?.["名义量程"] ?? 0;
          parts.push(fmt(nominal, el.modelId === "Simple Ammeter" ? "A" : "V"));
        }
        const text0 = parts.filter(Boolean).join(", ");
        if (text0) {
          const p0 = new THREE.Vector3(0, (g.userData.size?.y || 0.05) + 0.06, 0);
          g.localToWorld(p0);
          entries.push({ id: el.id, world: p0, text: text0 });
        }
        continue;
      }
      if ("电压" in st) parts.push(fmt(st["电压"], "V"));
      if ("电流" in st) parts.push(fmt(st["电流"], "A"));
      if ("功率" in st && !("电压" in st)) parts.push(fmt(st["功率"], "W"));
      // 数字状态（Logic Output / 触发器）：H/L
      if ("状态" in st) parts.push(st["状态"] ? "H" : "L");
      const text = parts.filter(Boolean).join(", ");
      if (!text) continue;
      const p = new THREE.Vector3(0, (g.userData.size?.y || 0.05) + 0.06, 0);
      g.localToWorld(p);
      entries.push({ id: el.id, world: p, text });
    }
    this.ui.updateLabels(entries, this.world.camera, this.world.renderer);
  }

  loop() {
    this._lastT = performance.now();
    this._clkAcc = 0;
    const render = () => {
      requestAnimationFrame(render);
      const now = performance.now();
      const dt = Math.min(0.1, (now - this._lastT) / 1000);
      this._lastT = now;
      // 数字时钟驱动（Unity Speed 档位：1s/s = 每秒 1 次 clk 步进）
      if (this.running && this.hasSimulated && this.engine.circuit) {
        const rate = [1, 2, 0.5, 0.2][this.speedIdx] ?? 1;
        this._clkAcc += dt * rate;
        if (this._clkAcc >= 1) {
          const steps = Math.floor(this._clkAcc);
          this._clkAcc -= steps;
          for (let i = 0; i < steps; i++) this.engine.digitalClk();
          this.scheduleSimulate();
        }
      }
      this.applyJoystick();
      this.world.controls.update();
      if (this.rails.selection) {
        const g = this.elementObjects.get(this.rails.selection);
        if (g) this._selectBox.setFromObject(g);
      }
      this.world.renderer.render(this.world.scene, this.world.camera);
      this.updateMeters(dt);
      this.updateLabels();

      this.frames = (this.frames || 0) + 1;
      // 复用本帧开头取的 now（841 行曾重复声明 const now，导致构建失败）
      if (!this.fpsStart) this.fpsStart = now;
      if (now - this.fpsStart >= 1000) {
        this.ui.setFps((this.frames * 1000) / (now - this.fpsStart));
        this.frames = 0;
        this.fpsStart = now;
      }
    };
    render();
  }

  frameTick() {}
}

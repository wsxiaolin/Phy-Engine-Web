// Component catalogue + chip pin conventions extracted from the Unity project.

let _catalog = null;
let _chips = null;

export async function loadCatalog() {
  if (_catalog) return _catalog;
  const [cat, chips] = await Promise.all([
    fetch(`${import.meta.env.BASE_URL}assets/catalog.json`).then((r) => r.json()),
    fetch(`${import.meta.env.BASE_URL}assets/chips.json`).then((r) => r.json()),
  ]);
  _catalog = cat;
  _chips = chips;
  return _catalog;
}

export function catalog() {
  return _catalog || [];
}

export function chipSpec(modelId) {
  return _chips ? _chips[modelId] : null;
}

export function byId(modelId) {
  return catalog().find((e) => e.ModelID === modelId) || null;
}

// Tab order matches the Unity Physics-Lab bottom sheet.
export const CATEGORY_ORDER = ["基础电路", "仪器仪表", "模拟电路", "家庭电路", "逻辑电路", "传感器", "演示元件"];

export function categories() {
  return CATEGORY_ORDER.filter((c) => catalog().some((e) => (e.Categories || []).includes(c)));
}

export function itemsIn(category) {
  return catalog().filter((e) => (e.Categories || []).includes(category));
}

// ModelIDs the engine backend can currently simulate (docs/ENGINE_API.md §4).
// 电表类例外：pe_model_id.h 无原生模型，仿真走 meters.js 的 Resistor 子网络
// 展开（Unity Meters/BuildElements 同构），故同样视为可仿真。
const SUPPORTED = new Set([
  "Ground Component", "Resistor", "Basic Capacitor", "Basic Inductor",
  "Battery Source", "Simple Switch", "Push Switch", "Air Switch",
  "Transformer", "Mutual Inductor", "Rectifier",
  "Logic Input", "Logic Output",
  "Or Gate", "And Gate", "Nand Gate", "Nor Gate", "Xor Gate", "Xnor Gate",
  "Imp Gate", "Nimp Gate", "Yes Gate", "No Gate", "Schmitt Trigger",
  "Comparator", "JK Flipflop", "T Flipflop", "Real-T Flipflop", "Multiplier",
  "D Flipflop", "Half Adder", "Full Adder", "Half Subtractor", "Full Subtractor",
  "Counter", "Random Generator",
  "Simple Ammeter", "Simple Voltmeter", "Galvanometer", "Microammeter",
  "Electricity Meter", "Multimeter",
]);

export function isSupported(modelId) {
  return SUPPORTED.has(modelId);
}

// Local pin anchors (metres, component space). Chips have no literal pins in the
// prefab; positions follow ChipComponent.OnPoolCreating (outputs left, inputs right).
export function pinsOf(modelId) {
  const entry = byId(modelId);
  if (!entry) return [];
  if (entry.pins && entry.pins.length) {
    return entry.pins.map((p, i) => ({ name: p.name || `Pin ${i + 1}`, position: p.position, isPositive: !!p.isPositive }));
  }
  const spec = chipSpec(modelId);
  if (!spec) return [];
  const outN = spec.outputs.length;
  const inN = spec.inputs.length;
  const pins = [];
  const zLerp = (i, n) => (n <= 1 ? 0 : -0.07 + (0.14 * i) / (n - 1));
  // Unity ChipComponent.OnPoolCreating: outputs x=-0.065 / inputs x=+0.065（Unity 空间）。
  // GLB 为镜像空间（x 取反），故此处 outputs=+0.065 / inputs=-0.065，与门电路 prefab 的
  // 实测 GLB pin 方向（inputs -0.06 / outputs +0.06）一致。
  for (let i = 0; i < outN; i++) pins.push({ name: spec.pins[spec.outputs[i]], position: [0.065, 0.02, zLerp(i, outN)], isPositive: true });
  for (let i = 0; i < inN; i++) pins.push({ name: spec.pins[spec.inputs[i]], position: [-0.065, 0.02, zLerp(i, inN)], isPositive: false });
  return pins;
}

// Wire colours mirror Unity DialogWires.WireColors.
export const WIRE_COLORS = [
  { name: "黑色导线", hex: 0x2b2b2b },
  { name: "蓝色导线", hex: 0x2f7de1 },
  { name: "红色导线", hex: 0xe0574a },
  { name: "绿色导线", hex: 0x3fae5a },
  { name: "黄色导线", hex: 0xe9c33a },
];

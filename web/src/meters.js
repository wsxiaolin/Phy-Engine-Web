// M8 电表类：Unity Meters 一比一前端展开。
// pe_sim 引擎无电表原生模型（pe_model_id.h 不含 Meters），此处照 Unity
// BuildElements 把电表展开为 Resistor 子网络送引擎求解，回读子电阻电压后
// 本地复算 Unity SyncStatistics 公式（电流/刻度/名义量程/烧毁）。
// 数值全部抄自 unity/Assets/Scripts/Circuits/Components/Meters/*.cs，禁止凭记忆改。
//
// 子电阻约定：side 'a' = Resistor pin0（正端）、'b' = pin1（负端）。
// 电表引脚（catalog pins）：Pin1(索引0)=负接线柱、Pin2(索引1)=正公共、
// Pin3(索引2)=量程档（0.6A/3A 或 3V/15V）；电能表 4 引脚。

export const METER_MODELS = new Set([
  "Simple Ammeter",
  "Simple Voltmeter",
  "Galvanometer",
  "Microammeter",
  "Electricity Meter",
]);

export function isMeter(modelId) {
  return METER_MODELS.has(modelId);
}

export function isIdeal(el) {
  return Number(el.properties?.["理想模式"]) === 1;
}

// 电表某引脚上的外部导线计数（档位判定用，Unity Pins[n].Connections.Count）。
export function pinWiredOf(wires, elId) {
  const counts = {};
  for (const w of wires) {
    if (w.source === elId) counts[w.sourcePin] = (counts[w.sourcePin] || 0) + 1;
    if (w.target === elId) counts[w.targetPin] = (counts[w.targetPin] || 0) + 1;
  }
  return counts;
}

// ---- 子网络定义（BuildElements + SyncProperties 数值）-----------------------
// r：电阻值；a/b：该子电阻正/负端对应的电表引脚节点（注释用）；
// pinMap：电表外部引脚 → 子电阻端点（外部导线改接目标）；
// internal：需要显式互连的节点对（Unity AbstractPin.Connect 的对应物）。

const NETWORKS = {
  "Simple Ammeter": {
    ideal: {
      // ideal: R1(Pins[1]→Pins[0]) = 1e-6，Pins[2] 挂 R1 正端
      resistors: [{ key: "R1", r: 1e-6 }],
      pinMap: { 0: ["R1", "b"], 1: ["R1", "a"], 2: ["R1", "a"] },
      internal: [],
    },
    real: {
      // real: R1(P2→P1)=1/72, R2(P2→P3)=0.1, R3(P3→P1)=0.025
      resistors: [
        { key: "R1", r: 1 / 72 },
        { key: "R2", r: 0.1 },
        { key: "R3", r: 0.025 },
      ],
      pinMap: { 0: ["R1", "b"], 1: ["R1", "a"], 2: ["R2", "b"] },
      internal: [
        ["R1", "a", "R2", "a"], // P2 节点
        ["R2", "b", "R3", "a"], // P3 节点
        ["R3", "b", "R1", "b"], // P1 节点
      ],
    },
  },
  "Simple Voltmeter": {
    ideal: {
      // ideal: R1(P2→P1) = 1e6，P3 挂 R1 正端
      resistors: [{ key: "R1", r: 1e6 }],
      pinMap: { 0: ["R1", "b"], 1: ["R1", "a"], 2: ["R1", "a"] },
      internal: [],
    },
    real: {
      // real: R1(P2→P1)=3000, R2(P3→P2)=12000
      resistors: [
        { key: "R1", r: 3000 },
        { key: "R2", r: 12000 },
      ],
      pinMap: { 0: ["R1", "b"], 1: ["R1", "a"], 2: ["R2", "a"] },
      internal: [["R1", "a", "R2", "b"]], // P2 节点
    },
  },
  "Galvanometer": {
    // 无理想模式：R1(P2→P1)=100, R2(P3→P2)=2400
    real: {
      resistors: [
        { key: "R1", r: 100 },
        { key: "R2", r: 2400 },
      ],
      pinMap: { 0: ["R1", "b"], 1: ["R1", "a"], 2: ["R2", "a"] },
      internal: [["R1", "a", "R2", "b"]], // P2 节点
    },
  },
  "Microammeter": {
    // 无理想模式：R1(P2→P1)=500, R2(P3→P2)=2000
    real: {
      resistors: [
        { key: "R1", r: 500 },
        { key: "R2", r: 2000 },
      ],
      pinMap: { 0: ["R1", "b"], 1: ["R1", "a"], 2: ["R2", "a"] },
      internal: [["R1", "a", "R2", "b"]], // P2 节点
    },
  },
  "Electricity Meter": {
    // 4 引脚：R_V(P1→P2)=1e9, R_C(P1→P3)=0.01, R2(P2→P4)=0.01
    real: {
      resistors: [
        { key: "RV", r: 1e9 },
        { key: "RC", r: 0.01 },
        { key: "R2", r: 0.01 },
      ],
      pinMap: { 0: ["RV", "a"], 1: ["RV", "b"], 2: ["RC", "b"], 3: ["R2", "b"] },
      internal: [
        ["RV", "a", "RC", "a"], // P1 节点
        ["RV", "b", "R2", "a"], // P2 节点
      ],
    },
  },
};

// ---- 展开函数 ---------------------------------------------------------------

// 把 elements/wires（均为可变副本）里的电表替换为子电阻网络。
// 返回 { elements, wires, meters:[{el, spec}] }；meters 供回读统计用。
export function expandMeters(elements, wires) {
  const out = [];
  const meters = [];
  const nets = []; // {el, net} wire 改写用
  for (const el of elements) {
    const nets4model = NETWORKS[el.modelId];
    if (!nets4model) {
      out.push(el);
      continue;
    }
    const ideal = isIdeal(el);
    let net = nets4model[ideal ? "ideal" : "real"] || nets4model.real;
    // 深拷贝网络（烧毁改写电阻值，避免污染共享常量）
    net = {
      resistors: net.resistors.map((r) => ({ ...r })),
      pinMap: { ...net.pinMap },
      internal: net.internal.map((x) => [...x]),
    };
    // 烧毁：Unity SyncProperties → SetResistance(this, 0, 1e8)
    if (el.broken) {
      const r0 = net.resistors.find((r) => r.key === "R1" || r.key === "RV");
      if (r0) r0.r = 1e8;
    }
    for (const r of net.resistors) {
      out.push({
        id: `${el.id}::${r.key}`,
        modelId: "Resistor",
        label: el.label,
        position: { ...el.position },
        rotY: el.rotY || 0,
        properties: { 电阻: r.r },
        statistics: {},
        broken: false,
      });
    }
    nets.push({ el, net });
    meters.push({ el });
  }
  // 改写外部导线端点：电表(id,pin) → 子电阻(id::key, pin0/1)
  const netOf = new Map(nets.map((n) => [n.el.id, n.net]));
  const wires2 = wires.map((w) => {
    const w2 = { ...w };
    for (const side of ["source", "target"]) {
      const pinSide = side === "source" ? "sourcePin" : "targetPin";
      const net = netOf.get(w2[side]);
      if (!net) continue;
      const dest = net.pinMap[w2[pinSide]];
      if (!dest) continue; // 引脚无映射：悬空端，丢弃该端（保持原样让引擎忽略）
      w2[side] = `${w2[side]}::${dest[0]}`;
      w2[pinSide] = dest[1] === "a" ? 0 : 1;
    }
    return w2;
  });
  // 内部互连导线（节点合并，Unity AbstractPin.Connect 对应物）
  for (const { el, net } of nets) {
    for (const [ka, sa, kb, sb] of net.internal) {
      wires2.push({
        source: `${el.id}::${ka}`,
        sourcePin: sa === "a" ? 0 : 1,
        target: `${el.id}::${kb}`,
        targetPin: sb === "a" ? 0 : 1,
        colorName: "黑色导线",
      });
    }
  }
  return { elements: out, wires: wires2, meters };
}

// ---- 统计公式（Unity SyncStatistics 一比一）---------------------------------
// U：{ R1: 电压, ... } 引擎回读的子电阻压降；pinWired：外部导线计数；
// dtSec：电能表累积步长（Unity Statistics.DeltaTime 对应物）。

function ohm(u, r) {
  return r > 0 ? u / r : 0;
}

function fmtStats(st) {
  const out = {};
  for (const [k, v] of Object.entries(st)) {
    out[k] = Number.isFinite(v) ? +v.toFixed(6) : v;
  }
  return out;
}

export function meterStatistics(el, U, pinWired, dtSec = 0) {
  const broken0 = !!el.broken;
  let st, broken = false;
  switch (el.modelId) {
    case "Simple Ammeter": {
      // 电流/功率/电压 = 主电阻 R1；量程 0.0075（满偏电压）
      const r1 = broken0 ? 1e8 : isIdeal(el) ? 1e-6 : 1 / 72;
      const u1 = U.R1 || 0;
      const i = ohm(u1, r1);
      const p = u1 * i;
      const u = i === 0 ? 0 : p / i;
      const nominal = pinWired[1] ? 0.6 : 3; // P2 有连接→0.6 档，否则 3 档
      const scale = isIdeal(el) ? i / nominal : u / 0.0075;
      st = { 电流: i, 功率: p, 电压: u, 刻度: scale, 名义量程: nominal };
      // Unity 两条独立 if：P2 接线→刻度×0.6；P3 接线→刻度×3（后者覆盖）
      st.名义电流 = pinWired[2] ? scale * 3 : scale * nominal;
      broken = broken0 || scale < -0.38 || scale > 1.05;
      break;
    }
    case "Simple Voltmeter": {
      // 量程 0.001（满偏电流）；名义量程 3/15V
      const r1 = broken0 ? 1e8 : isIdeal(el) ? 1e6 : 3000;
      const u1 = U.R1 || 0;
      const i = ohm(u1, r1);
      const p = u1 * i;
      const u = i === 0 ? 0 : p / i;
      const nominal = pinWired[1] ? 3 : 15;
      const scale = isIdeal(el) ? u / nominal : i / 0.001;
      st = { 电流: i, 功率: p, 电压: u, 刻度: scale, 名义量程: nominal };
      st.名义电压 = pinWired[2] ? scale * 15 : scale * nominal;
      broken = broken0 || scale < -0.38 || scale > 1.05;
      break;
    }
    case "Galvanometer": {
      // 量程 3e-6 A；刻度取负（指针双向，中零）
      const r1 = broken0 ? 1e8 : 100;
      const u1 = U.R1 || 0;
      const i = ohm(u1, r1);
      const p = u1 * i;
      const u = i === 0 ? 0 : p / i;
      const scale = -i / 3e-6;
      st = { 电流: i, 功率: p, 电压: u, 刻度: scale, 量程: 3e-6 };
      broken = broken0 || scale < -1.05 || scale > 1.05;
      break;
    }
    case "Microammeter": {
      // 量程 0.1V（卡片显示 0.2，计算用 0.1——照抄源码）
      const r1 = broken0 ? 1e8 : 500;
      const u1 = U.R1 || 0;
      const i = ohm(u1, r1);
      const p = u1 * i;
      const u = i === 0 ? 0 : p / i;
      const scale = u / 0.1;
      st = { 电流: i, 功率: p, 电压: u, 刻度: scale, 量程: 0.1 };
      broken = broken0 || scale < -0.38 || scale > 1.05;
      break;
    }
    case "Electricity Meter": {
      // 电流=RC 支路、电压=RV 压降、示数 Wh 累积；额定电流 6A
      const rated = Number(el.properties?.["额定电流"]) || 6;
      const uV = U.RV || 0;
      const uC = U.RC || 0;
      const i = broken0 ? 0 : ohm(uC, 0.01);
      const u = broken0 ? 0 : uV;
      const p = i * u;
      const prev = Number(el.properties?.["示数"]) || 0;
      const wh = prev + p * dtSec / 3600;
      el.properties = el.properties || {};
      el.properties["示数"] = +wh.toFixed(6);
      st = { 电流: i, 电压: u, 功率: p, 示数: +wh.toFixed(6), 额定电流: rated };
      broken = broken0 || i < -rated || i > rated;
      break;
    }
    default:
      return null;
  }
  if (broken) st.烧毁 = 1;
  return { statistics: fmtStats(st), broken };
}

// ---- 指针规格（Unity RenderPointer：eulerY = lerp(46°, -46°, invLerp(min,max,v))）

export const POINTER_SPEC = {
  "Simple Ammeter": { node: "指针", min: -1 / 3, max: 1, value: (st) => st.刻度 },
  "Simple Voltmeter": { node: "指针", min: -1 / 3, max: 1, value: (st) => st.刻度 },
  "Galvanometer": { node: "指针", min: -1, max: 1, value: (st) => st.刻度 },
  "Microammeter": { node: "指针", min: 0, max: 1, value: (st) => st.刻度 },
  // 电能表无指针（Unity 用 Text 数字滚轮，web 端读数行显示）
};

// 指针目标角（弧度）；未连接 → 0 值；烧毁 → null（冻结，Unity Render 同语义）
export function pointerAngle(modelId, statistics, broken) {
  const spec = POINTER_SPEC[modelId];
  if (!spec) return null;
  if (broken) return null;
  const connected = statistics && Object.keys(statistics).length > 0;
  const v = connected ? Number(statistics["刻度"]) || 0 : 0;
  const t = Math.max(0, Math.min(1, (v - spec.min) / (spec.max - spec.min)));
  const deg = 46 + t * (-92); // lerp(46, -46, t)
  return (deg * Math.PI) / 180;
}

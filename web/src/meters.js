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
  "Multimeter",
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

// ---- Multimeter（多用电表）---------------------------------------------------
// Unity Meters/Multimeter.cs 一比一。网络与档位联动（GetStatusData 0..17）：
// BuildElements = R(Pins[0]→内部) + VDC(内部→Pins[1], MaximumVoltage 按档位)。
// web 侧 VDC 用引擎 Battery Source（VDC 模型，属性「电压」）子元件承载，
// pin0=正=内部节点、pin1=负=Pins[1]（与 app.js 幽灵接地「电池负=pin1」约定一致）。

export function multimeterMode(el) {
  const m = Math.round(Number(el.properties?.["状态"]) || 0);
  return Math.max(0, Math.min(17, m));
}

// SyncProperties 三段（Unity 源码逐 case 抄录）：
// 档 0-2,13-17（OFF/交流/直流电压）：R=1e9, V=0（伏特计形态，并联）；
// 档 3-7（直流电流）：R=1e-9, V=0（安培计形态，串联）；
// 档 8-12（电阻）：R=1, V=-15（内置 15V 驱动源，实测 R=15/I-1）。
function multimeterNet(el) {
  const mode = multimeterMode(el);
  const ohmMode = mode >= 8 && mode <= 12;
  const r = ohmMode ? 1 : mode >= 3 && mode <= 7 ? 1e-9 : 1e9;
  return {
    resistors: [{ key: "R1", r }],
    sources: [{ key: "SRC", v: ohmMode ? -15 : 0 }],
    pinMap: { 0: ["R1", "a"], 1: ["SRC", "b"] },
    internal: [["R1", "b", "SRC", "a"]],
  };
}

// 18 档档位表：label = GetStatusData 的 OperationData(值,单位,说明) 三字段
// 组合；angle = Render 的 SwitchKnob localEulerAngles.y 逐 case 抄录。
// 注：GLB 无 SwitchKnob 节点（旋钮烤在主体网格里，dump_glb 实证 4 网格无
// 旋钮件），旋钮转角暂不驱动，数值保留在此待后续建模拆分。
export const MULTIMETER_MODES = [
  { label: "开关开路", angle: 0 },
  { label: "交流 750V", angle: 15.2 },
  { label: "交流 200V", angle: 35 },
  { label: "直流 0.0002A", angle: 52 },
  { label: "直流 0.002A", angle: 72.5 },
  { label: "直流 0.02A", angle: 91 },
  { label: "直流 0.2A", angle: 108 },
  { label: "直流 10A", angle: 125.3 },
  { label: "电阻 200Ω", angle: 180 },
  { label: "电阻 2000Ω", angle: 198 },
  { label: "电阻 20000Ω", angle: 216 },
  { label: "电阻 200000Ω", angle: 231 },
  { label: "电阻 2000000Ω", angle: 250 },
  { label: "直流 0.2V", angle: 265.5 },
  { label: "直流 2V", angle: 284 },
  { label: "直流 20V", angle: 302 },
  { label: "直流 200V", angle: 318 },
  { label: "直流 1000V", angle: 337 },
];

// Unity GetDigitalText 一比一：|v|≥max→"OL"；≤min 或非有限→"0.00"；
// 否则 (负号)+|v|.ToString()，长度≥7 截前 7 字符。
function digital(src, max, min) {
  if (!Number.isFinite(src)) return "0.00";
  const a = Math.abs(src);
  if (a >= max) return "OL";
  if (a <= min) return "0.00";
  const s = (src < 0 ? "-" : "") + String(a);
  return s.length >= 7 ? s.slice(0, 7) : s;
}

// Unity Math.Round(x, n) 为银行家舍入，此处 half-up；仅精确 .5 边界有差异。
const roundN = (v, n) => {
  const m = 10 ** n;
  return Math.round(v * m) / m;
};

// Render() 的 TextDisplay 数字显字（档位 + 统计键 → 屏显字符串）。
// 电阻档实测值 = 15/瞬间电流-1（Unity Render 原式）。
export function multimeterDisplay(el, st) {
  const mode = multimeterMode(el);
  const V = Number(st?.电压) || 0; // Unity sqrt(|P·R|) ≥ 0（幅值）
  const I = Number(st?.瞬间电流) || 0;
  const Uv = Number(st?.瞬间电压) || 0; // 带符号
  const R = I !== 0 ? 15 / I - 1 : Infinity;
  switch (mode) {
    case 0: return "";
    case 1: return digital(roundN(V, 2), 750, 1);
    case 2: return digital(roundN(V, 2), 250, 0.1);
    case 3: return digital(I, 0.0002, 1e-8);
    case 4: return digital(I, 0.002, 1e-7);
    case 5: return digital(I, 0.02, 1e-6);
    case 6: return digital(I, 0.2, 1e-4);
    case 7: return digital(roundN(I, 2), 10, 0.01);
    case 8: return digital(roundN(R, 1), 200, 1);
    case 9: return digital(Math.round(R), 2000, 10);
    case 10: return digital(Math.round(R), 20000, 100);
    case 11: return digital(Math.round(R), 200000, 1000);
    case 12: return digital(Math.round(R), 2000000, 10000);
    case 13: return digital(roundN(Uv, 4), 0.2, 0.001);
    case 14: return digital(roundN(Uv, 3), 2, 0.01);
    case 15: return digital(roundN(Uv, 3), 20, 0.1);
    case 16: return digital(roundN(Uv, 2), 200, 1);
    case 17: return digital(roundN(Uv, 2), 1000, 10);
  }
  return "";
}

// ---- 展开函数 ---------------------------------------------------------------
// 把 elements/wires（均为可变副本）里的电表替换为子电阻网络。
// 返回 { elements, wires, meters:[{el, spec}] }；meters 供回读统计用。
export function expandMeters(elements, wires) {
  const out = [];
  const meters = [];
  const nets = []; // {el, net} wire 改写用
  for (const el of elements) {
    const isMM = el.modelId === "Multimeter";
    const nets4model = NETWORKS[el.modelId];
    if (!isMM && !nets4model) {
      out.push(el);
      continue;
    }
    const ideal = isIdeal(el);
    let net = isMM ? multimeterNet(el) : nets4model[ideal ? "ideal" : "real"] || nets4model.real;
    // 深拷贝网络（烧毁改写电阻值，避免污染共享常量；Multimeter 无烧毁逻辑）
    net = {
      resistors: net.resistors.map((r) => ({ ...r })),
      sources: (net.sources || []).map((s) => ({ ...s })),
      pinMap: { ...net.pinMap },
      internal: net.internal.map((x) => [...x]),
    };
    // 烧毁：Unity SyncProperties → SetResistance(this, 0, 1e8)
    if (el.broken && !isMM) {
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
    // Multimeter 内置源（Unity VoltageSource DC，MaximumVoltage 按档位 -15/0）：
    // 引擎侧用 Battery Source（属性「电压」）承载，负值直传（MNA 代数无歧义）。
    for (const s of net.sources) {
      out.push({
        id: `${el.id}::${s.key}`,
        modelId: "Battery Source",
        label: el.label,
        position: { ...el.position },
        rotY: el.rotY || 0,
        properties: { 电压: s.v },
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
      const u1 = U.R1?.电压 || 0;
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
      const u1 = U.R1?.电压 || 0;
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
      const u1 = U.R1?.电压 || 0;
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
      const u1 = U.R1?.电压 || 0;
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
      const uV = U.RV?.电压 || 0;
      const uC = U.RC?.电压 || 0;
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
    case "Multimeter": {
      // Unity SyncStatistics → SyncResistor(this, Statistics, 0, Resistance)：
      // 瞬间电流=I(U/R1)、瞬间电压=P/I、电压=√|P·R|（幅值，AC 档用）、
      // 电流=√|P/R|。R1 取档位值（multimeterNet 与 expandMeters 同源）。
      // 无烧毁判定（Multimeter.cs 源码无 Break 逻辑）。
      const mmNet = multimeterNet(el);
      const mmR = mmNet.resistors[0].r;
      const mmU = U.R1?.电压 || 0;
      let mmI = ohm(mmU, mmR);
      // 电流档 R1=1e-9Ω 压降 ~1e-11V：引擎序列化截断归零时改读内置源支路
      // 电流（MNA write_back 回填 V 源支路电流，串联同值；符号以 e2e 实证校准）
      const srcI = Number(U.SRC?.电流) || 0;
      if (mmI === 0 && srcI !== 0) mmI = srcI;
      const mmP = mmU * mmI;
      st = {
        瞬间电流: mmI,
        瞬间电压: mmI === 0 ? 0 : mmP / mmI,
        电压: Math.sqrt(Math.abs(mmP * mmR)),
        电流: Math.sqrt(Math.abs(mmP / mmR)),
        功率: mmP,
      };
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

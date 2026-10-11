// Experiment document: the same Elements/Wires structure stored in a .plsave
// (Unity-compatible JSON). The frontend owns this and hands it to the engine.

let _idCounter = 0;
function newId(modelId) {
  _idCounter += 1;
  const rnd = Math.random().toString(16).slice(2, 10);
  return `${modelId.replace(/\W/g, "")}-${Date.now().toString(36)}-${_idCounter}-${rnd}`;
}

// Sensible starting properties so freshly placed parts build in the engine.
const DEFAULT_PROPS = {
  "Resistor": { 电阻: 100 },
  "Basic Capacitor": { 电容: 0.001 },
  "Basic Inductor": { 电感: 0.001 },
  "Battery Source": { 电压: 3 },
  "Simple Switch": { 开关: 0 },
  "Push Switch": { 开关: 0 },
  "Air Switch": { 开关: 0 },
  "Transformer": { 输入电压: 10, 输出电压: 5 },
  "Mutual Inductor": { 电感1: 0.001, 电感2: 0.001, 耦合系数: 0.5 },
  "Logic Input": { 开关: 0 },
  "Comparator": { Hl: 2, Ll: 1 },
};

export function defaultProps(modelId) {
  return { ...(DEFAULT_PROPS[modelId] || {}) };
}

export class Experiment {
  constructor() {
    this.elements = [];
    this.wires = [];
  }

  clear() {
    this.elements = [];
    this.wires = [];
  }

  addElement({ modelId, label, position, rotY = 0, properties = {}, statistics = {}, identifier = null }) {
    const el = {
      id: identifier || newId(modelId),
      modelId,
      label,
      position: { ...position },
      rotY,
      properties,
      statistics: { ...statistics },
      broken: false,
    };
    this.elements.push(el);
    return el;
  }

  removeElement(id) {
    this.elements = this.elements.filter((e) => e.id !== id);
    this.wires = this.wires.filter((w) => w.source !== id && w.target !== id);
  }

  getElement(id) {
    return this.elements.find((e) => e.id === id) || null;
  }

  addWire(source, sourcePin, target, targetPin, colorName) {
    if (source === target) return null;
    const dup = this.wires.find(
      (w) => w.source === source && w.sourcePin === sourcePin && w.target === target && w.targetPin === targetPin,
    );
    if (dup) return null;
    const w = { source, sourcePin, target, targetPin, colorName };
    this.wires.push(w);
    return w;
  }

  removeWire(w) {
    this.wires = this.wires.filter((x) => x !== w);
  }

  // Serialise to the Unity .plsave envelope the engine consumes.
  // 注意：.plsave 的 Rotation 是【角度】（Unity 约定，引擎默认值 "0,180,0"），
  // 前端内部 rotY 用弧度，此处转换。
  toPlsave(camera = { VisionCenter: "0,0,0", TargetRotation: "0,0,0" }) {
    const deg = (rad) => +((rad * 180) / Math.PI).toFixed(4);
    const StatusSave = {
      Elements: this.elements.map((e) => ({
        ModelID: e.modelId,
        Identifier: e.id,
        Label: e.label,
        Position: `${e.position.x},${e.position.y},${e.position.z}`,
        Rotation: `0,${deg(e.rotY || 0)},0`,
        Properties: e.properties,
        Statistics: e.statistics,
        IsBroken: e.broken,
      })),
      Wires: this.wires.map((w) => ({
        Source: w.source,
        SourcePin: w.sourcePin,
        Target: w.target,
        TargetPin: w.targetPin,
        ColorName: w.colorName,
      })),
    };
    return {
      Type: 0,
      CameraSave: JSON.stringify(camera),
      StatusSave: JSON.stringify(StatusSave),
    };
  }

  static fromPlsave(root) {
    const exp = new Experiment();
    const experiment = root.Experiment || root;
    let status = experiment.StatusSave;
    if (typeof status === "string") status = JSON.parse(status || "{}");
    status = status || {};
    const rawElements = Array.isArray(status.Elements)
      ? status.Elements
      : Object.values(status.Elements || {});
    for (const e of rawElements) {
      const [x, y, z] = (e.Position || "0,0,0").split(",").map(Number);
      // .plsave Rotation 是角度，前端内部弧度
      const rotDeg = Number(((e.Rotation || "0,0,0").split(",")[1]) || 0);
      exp.addElement({
        modelId: e.ModelID,
        label: e.Label || e.ModelID,
        position: { x, y, z },
        rotY: (rotDeg * Math.PI) / 180,
        properties: e.Properties || {},
        statistics: e.Statistics || {},
        identifier: e.Identifier,
      });
    }
    for (const w of status.Wires || []) {
      exp.wires.push({
        source: w.Source,
        sourcePin: w.SourcePin,
        target: w.Target,
        targetPin: w.TargetPin,
        colorName: w.ColorName || "黑色导线",
      });
    }
    return exp;
  }
}

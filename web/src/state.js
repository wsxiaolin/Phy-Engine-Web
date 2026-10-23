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
  "Multimeter": { 状态: 0 },
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

  addElement({ modelId, label, position, rotY = 0, properties = {}, statistics = {}, identifier = null, broken = false }) {
    const el = {
      id: identifier || newId(modelId),
      modelId,
      label,
      position: { ...position },
      rotY,
      properties,
      statistics: { ...statistics },
      broken,
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

  // Serialise to the native .plsave envelope. Field-for-field mirror of the
  // engine's own writer (repo physicslab.h: default_plsav_template[circuit] +
  // to_plsav_json_ec), so the exported file is byte-schema identical to what
  // Unity 2.0 / the engine produce: root { Type, ID, Experiment{...Version 2404,
  // Paused, ...}, Summary{...}, CreationDate, Speed*, CameraSnapshot, Plots... }.
  // 注意：.plsave 的 Rotation 是【角度】（Unity 约定，引擎默认值 "0,180,0"），
  // 前端内部 rotY 用弧度，此处转换。
  // 引擎 experiment::create(circuit) 相机默认（physicslab.h:778-782）：
  // Mode 0 / Distance 2.7 / VisionCenter {0,-0.45,1.08} / TargetRotation {50,0,0}。
  toPlsave(camera = { Mode: 0, Distance: 2.7, VisionCenter: "0,-0.45,1.08", TargetRotation: "50,0,0" }) {
    const deg = (rad) => +((rad * 180) / Math.PI).toFixed(4);
    const StatusSave = {
      SimulationSpeed: 1,
      Elements: this.elements.map((e) => ({
        ModelID: e.modelId,
        Identifier: e.id,
        Label: e.label,
        Position: `${e.position.x},${e.position.y},${e.position.z}`,
        Rotation: `0,${deg(e.rotY || 0)},0`,
        Properties: e.properties,
        Statistics: e.statistics,
        IsBroken: e.broken,
        // 引擎 element 构造器同款字段（physicslab.h element::create 数据模板），
        // Unity 端缺省可读，写全保证与引擎 dump 形状一致。
        IsLocked: false,
        DiagramCached: false,
        DiagramPosition: { X: 0, Y: 0, Magnitude: 0 },
        DiagramRotation: 0,
      })),
      // 引擎 wire::to_json 恒写 5 键（wire 内部 color 缺省 blue），undefined 归一默认色
      Wires: this.wires.map((w) => ({
        Source: w.source,
        SourcePin: w.sourcePin,
        Target: w.target,
        TargetPin: w.targetPin,
        ColorName: w.colorName ?? "蓝色导线",
      })),
    };
    // 引擎 to_plsav_json_ec 同款：Experiment.CreationDate 与 Summary.CreationDate 均写毫秒
    const creationDate = Date.now();
    return {
      Type: 0,
      Experiment: {
        ID: null,
        Type: 0,
        Components: this.elements.length,
        Subject: null,
        StatusSave: JSON.stringify(StatusSave),
        CameraSave: JSON.stringify(camera),
        Version: 2404,
        CreationDate: creationDate,
        Paused: false,
        Summary: null,
        Plots: null,
      },
      ID: null,
      // 社区元数据模板（引擎 default_plsav_template Summary 分支逐字段抄录）
      Summary: {
        Type: 0,
        ParentID: null,
        ParentName: null,
        ParentCategory: null,
        ContentID: null,
        Editor: null,
        Coauthors: [],
        Description: null,
        LocalizedDescription: null,
        Tags: ["Type-0"],
        ModelID: null,
        ModelName: null,
        ModelTags: [],
        Version: 0,
        Language: "Chinese",
        Visits: 0,
        Stars: 0,
        Supports: 0,
        Remixes: 0,
        Comments: 0,
        Price: 0,
        Popularity: 0,
        CreationDate: creationDate,
        UpdateDate: 0,
        SortingDate: 0,
        ID: null,
        Category: null,
        Subject: "",
        LocalizedSubject: null,
        Image: 0,
        ImageRegion: 0,
        User: {
          ID: null,
          Nickname: null,
          Signature: null,
          Avatar: 0,
          AvatarRegion: 0,
          Decoration: 0,
          Verification: null,
        },
        Visibility: 0,
        Settings: {},
        Anonymous: false,
        Multilingual: false,
      },
      CreationDate: 0,
      Speed: 1,
      SpeedMinimum: 0.0002,
      SpeedMaximum: 2,
      SpeedReal: 0,
      Paused: false,
      Version: 0,
      CameraSnapshot: null,
      Plots: [],
      Widgets: [],
      WidgetGroups: [],
      Bookmarks: {},
      Interfaces: { "Play-Expanded": false, "Chart-Expanded": false },
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
        broken: !!e.IsBroken,
      });
    }
    for (const w of status.Wires || []) {
      exp.wires.push({
        source: w.Source,
        sourcePin: w.SourcePin,
        target: w.Target,
        targetPin: w.TargetPin,
        // 引擎 parse_wire_color_name：缺省/无法识别 → 蓝色导线，保持同判
        colorName: w.ColorName || "蓝色导线",
      });
    }
    return exp;
  }
}

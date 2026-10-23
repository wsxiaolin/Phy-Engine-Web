// M8/§7 存档专项 e2e：.plsave 信封一比一（规范 §7 双向兼容）。
// 跑法：node tools/verify_plsave.mjs
// 三重断言：
//   A. Node 直跑 state.js——toPlsave() 输出与引擎 default_plsav_template +
//      to_plsav_json_ec（physicslab.h:320/1215）逐键比对（root/Experiment/
//      Summary/元件/导线/相机默认全字段），fromPlsave() 往返还原。
//   B. WASM 引擎实测——把 toPlsave() 产物（新嵌套信封）直接喂
//      _pl_experiment_load_from_string，build→analyze→write_back→dump，
//      证明 web 导出文件引擎可装、物理正确（I=U/R）、信封字段透传不丢。
//   C. 旧扁平格式仍被引擎接受（load_from_json_ec else 分支，向后兼容）。
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const { Experiment } = await import(join(here, "../web/src/state.js"));

let fails = 0;
const ok = (cond, name) => {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}`);
  if (!cond) fails++;
};
const keyset = (o) => Object.keys(o).sort().join(",");

// ---------- A. 信封逐键比对（引擎模板物理抄录，禁记忆） ----------
const exp = new Experiment();
const elBat = exp.addElement({ modelId: "Battery Source", label: "电池", position: { x: -0.2, y: 0, z: 0 }, properties: { 电压: 3 }, statistics: { 电压: 3, 电流: 0.03 }, identifier: "bat1" });
const elRes = exp.addElement({ modelId: "Resistor", label: "电阻", position: { x: 0.2, y: 0, z: 0 }, rotY: Math.PI / 2, properties: { 电阻: 100 }, identifier: "r1" });
elRes.broken = true; // 烧毁位往返
const elSw = exp.addElement({ modelId: "Simple Switch", label: "开关", position: { x: 0, y: 0, z: 0.15 }, properties: { 开关: 1 }, identifier: "sw1" });
const elGnd = exp.addElement({ modelId: "Ground Component", label: "接地", position: { x: 0, y: 0, z: 0.3 }, identifier: "gnd1" });
exp.addWire("bat1", 0, "r1", 0, "黑色导线");
exp.addWire("r1", 1, "sw1", 0, "红色导线");
exp.addWire("sw1", 1, "bat1", 1, "绿色导线");
exp.addWire("bat1", 1, "gnd1", 0, undefined); // 无 ColorName → fromPlsave 应判蓝色

const sav = exp.toPlsave();
ok(keyset(sav) === "Bookmarks,CameraSnapshot,CreationDate,Experiment,ID,Interfaces,Paused,Plots,Speed,SpeedMaximum,SpeedMinimum,SpeedReal,Summary,Type,Version,WidgetGroups,Widgets"
  && sav.Type === 0 && sav.ID === null && sav.CreationDate === 0 && sav.Speed === 1
  && sav.SpeedMinimum === 0.0002 && sav.SpeedMaximum === 2 && sav.SpeedReal === 0
  && sav.Paused === false && sav.Version === 0 && sav.CameraSnapshot === null
  && Array.isArray(sav.Plots) && Array.isArray(sav.Widgets) && Array.isArray(sav.WidgetGroups)
  && sav.Bookmarks && typeof sav.Bookmarks === "object"
  && sav.Interfaces["Play-Expanded"] === false && sav.Interfaces["Chart-Expanded"] === false,
  "A1 root 信封 17 键与引擎 default_plsav_template 逐字段一致");

const E = sav.Experiment;
ok(keyset(E) === "CameraSave,Components,CreationDate,ID,Paused,Plots,StatusSave,Subject,Summary,Type,Version"
  && E.Type === 0 && E.ID === null && E.Components === 4 && E.Subject === null
  && E.Version === 2404 && E.Paused === false && E.Summary === null && E.Plots === null
  && Number.isFinite(E.CreationDate) && E.CreationDate > 1e12, // 毫秒时间戳
  "A2 Experiment 键集/Version 2404/Components 计数/CreationDate 毫秒");

const S = sav.Summary;
ok(keyset(S) === "Anonymous,Category,Coauthors,Comments,ContentID,CreationDate,Description,Editor,ID,Image,ImageRegion,Language,LocalizedDescription,LocalizedSubject,ModelID,ModelName,ModelTags,Multilingual,ParentCategory,ParentID,ParentName,Popularity,Price,Remixes,Settings,SortingDate,Stars,Subject,Supports,Tags,Type,UpdateDate,User,Version,Visibility,Visits"
  && S.Type === 0 && JSON.stringify(S.Tags) === '["Type-0"]' && S.Language === "Chinese"
  && S.Subject === "" && Array.isArray(S.Coauthors) && Array.isArray(S.ModelTags)
  && S.Version === 0 && S.UpdateDate === 0 && S.SortingDate === 0 && S.CreationDate === E.CreationDate
  && keyset(S.User) === "Avatar,AvatarRegion,Decoration,ID,Nickname,Signature,Verification"
  && S.Visibility === 0 && S.Settings && typeof S.Settings === "object"
  && S.Anonymous === false && S.Multilingual === false,
  "A3 Summary 36 键社区元数据模板与引擎逐键一致（physicslab.h:345-376，Version 在 Summary 级、Verification 只在 User 级）");

const cam = JSON.parse(E.CameraSave);
ok(cam.Mode === 0 && cam.Distance === 2.7 && cam.VisionCenter === "0,-0.45,1.08" && cam.TargetRotation === "50,0,0",
  "A4 相机默认 = 引擎 experiment::create(circuit)（physicslab.h:778-782）");

const status = JSON.parse(E.StatusSave);
ok(status.SimulationSpeed === 1 && Array.isArray(status.Elements) && status.Elements.length === 4 && Array.isArray(status.Wires),
  "A5 StatusSave 字符串可解析、SimulationSpeed=1（to_plsav_json_ec 同款）");
const el0 = status.Elements.find((e) => e.Identifier === "r1");
const elB0 = status.Elements.find((e) => e.Identifier === "bat1");
ok(keyset(el0) === "DiagramCached,DiagramPosition,DiagramRotation,Identifier,IsBroken,IsLocked,Label,ModelID,Position,Properties,Rotation,Statistics"
  && el0.ModelID === "Resistor" && el0.Label === "电阻" && el0.IsBroken === true && el0.IsLocked === false
  && el0.DiagramCached === false && keyset(el0.DiagramPosition) === "Magnitude,X,Y" && el0.DiagramRotation === 0
  && el0.Rotation === "0,90,0" && el0.Position === "0.2,0,0"
  && el0.Properties.电阻 === 100
  && elB0.Statistics.电压 === 3 && elB0.Statistics.电流 === 0.03,
  "A6 元件 12 键全字段（Label/IsLocked/Diagram* 引擎 element::create 同款）+ Rotation 角度制");
ok(status.Wires.every((w) => keyset(w) === "ColorName,Source,SourcePin,Target,TargetPin")
  && status.Wires[0].ColorName === "黑色导线" && status.Wires[3].ColorName === "蓝色导线",
  "A7 导线恒 5 键（引擎 wire::to_json 同款），未设色导线归一蓝色导线");

// ---------- A2. fromPlsave 往返 ----------
const back = Experiment.fromPlsave(sav);
const rRes = back.elements.find((e) => e.id === "r1");
const rBat = back.elements.find((e) => e.id === "bat1");
ok(back.elements.length === 4 && back.wires.length === 4
  && rBat.modelId === "Battery Source" && rBat.label === "电池"
  && rBat.properties.电压 === 3 && rBat.statistics.电压 === 3 && rBat.statistics.电流 === 0.03
  && rRes.broken === true && Math.abs(rRes.rotY - Math.PI / 2) < 1e-6
  && rRes.position.x === 0.2 && rRes.position.z === 0
  && back.wires[1].colorName === "红色导线" && back.wires[2].colorName === "绿色导线"
  && back.wires[3].colorName === "蓝色导线",
  "A8 fromPlsave 往返：标识/属性/统计/烧毁位/弧度/坐标/五色 + 缺省色=蓝色导线（引擎 parse_wire_color_name 同判）");

// 旧扁平格式（root 无 Experiment 键）仍可导入
const flat = { Type: 0, StatusSave: E.StatusSave, CameraSave: E.CameraSave };
const backFlat = Experiment.fromPlsave(flat);
ok(backFlat.elements.length === 4 && backFlat.wires.length === 4, "A9 旧扁平格式导入兼容（root.Experiment||root）");

// ---------- B. WASM 引擎装载新信封 ----------
const wasmDir = process.env.WASM_DIR || join(here, "../build/wasm");
const { default: createModule } = await import(join(wasmDir, "phy_engine.js"));
const M = await createModule({ wasmBinary: readFileSync(join(wasmDir, "phy_engine.wasm")) });
const enc = new TextEncoder();
const readCStr = (ptr) => { let e = ptr; while (M.HEAPU8[e] !== 0) e++; return new TextDecoder().decode(M.HEAPU8.subarray(ptr, e)); };
const loadStr = (s) => { const b = enc.encode(s); const p = M._malloc(b.length + 1); M.HEAPU8.set(b, p); M.HEAPU8[p + b.length] = 0; const h = M._pl_experiment_load_from_string(p, b.length); M._free(p); return h; };

const exB = loadStr(JSON.stringify(sav));
ok(!!exB, "B1 引擎装载 web toPlsave() 嵌套信封（load_from_json_ec Experiment 分支）");
const circ = M._pl_pe_circuit_build(exB);
ok(!!circ, "B2 build");
ok(M._pl_pe_circuit_set_analyze_type(circ, 0) === 0 && M._pl_pe_circuit_analyze(circ) === 0, "B3 analyze(OP)");
M._pl_pe_circuit_digital_clk(circ);
ok(M._pl_pe_circuit_write_back_to_pl(circ, exB) === 0, "B4 write_back");
const dump = readCStr(M._pl_experiment_dump(exB, 0));
const root = JSON.parse(dump);
ok(root.Experiment && root.Experiment.Version === 2404 && root.Summary && root.Summary.Language === "Chinese",
  "B5 dump 回读信封字段透传（Version/Summary 不丢）");
const st = JSON.parse(root.Experiment.StatusSave);
const byId = new Map(st.Elements.map((e) => [e.Identifier, e]));
const iLoop = Math.abs(byId.get("sw1").Statistics["电流"]);
const vR = byId.get("r1").Statistics["电压"];
ok(Math.abs(iLoop - 0.03) < 1e-6 && Math.abs(vR - 3) < 1e-6, `B6 物理正确 I=${iLoop}(=3/100) U_r=${vR}(=3)`);
const rB = byId.get("r1");
ok(rB.IsBroken === true && rB.Label === "电阻" && rB.DiagramCached === false && rB.IsLocked === false,
  "B7 引擎回读保留 web 写入的 12 键元件字段");
M._pl_pe_circuit_destroy(circ);
M._pl_experiment_destroy(exB);

// ---------- C. 引擎仍收旧扁平格式（向后兼容，smoke 同款） ----------
const exC = loadStr(JSON.stringify(flat));
ok(!!exC, "C1 引擎装载旧扁平格式（else 分支）");
M._pl_experiment_destroy(exC);

console.log(fails === 0 ? `\nPLSAVE VERIFY: ${"ALL PASS"} (A1-A9/B1-B7/C1)` : `\nPLSAVE VERIFY: ${fails} FAIL`);
process.exit(fails === 0 ? 0 : 1);

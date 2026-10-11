// Phy-Engine WASM smoke test (Node)
// Chain: create experiment -> load .plsave JSON -> build circuit -> analyze
//        -> write back -> dump. Proves the whole engine path works pre-frontend.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const wasmDir = process.env.WASM_DIR || join(here, "../build/wasm");
const { default: createModule } = await import(join(wasmDir, "phy_engine.js"));

// Node cannot fetch() file URLs — hand the wasm binary over directly.
const Module = await createModule({
  wasmBinary: readFileSync(join(wasmDir, "phy_engine.wasm"))
});
const M = Module;

const enc = new TextEncoder();
const dec = new TextDecoder();

function allocStr(s) {
  const bytes = enc.encode(s);
  const ptr = M._malloc(bytes.length + 1);
  M.HEAPU8.set(bytes, ptr);
  M.HEAPU8[ptr + bytes.length] = 0;
  return ptr;
}
function readCStr(ptr) {
  if (!ptr) return null;
  let end = ptr;
  while (M.HEAPU8[end] !== 0) end++;
  return dec.decode(M.HEAPU8.subarray(ptr, end));
}
function callStr(fn, ...args) {
  const out = fn(...args);
  const s = readCStr(out);
  if (out) M._free(out);
  return s;
}

const err = () => readCStr(M._phy_engine_last_error());

// ---- a battery + resistor + switch loop, Unity .plsave StatusSave style ----
// A ground reference is mandatory: without it the MNA matrix is singular and
// circuit_analyze() fails. Unity Physics-Lab circuits always carry a ground.
const VBAT = 3.0;
const R = 100.0;
const elements = [
  { ModelID: "Battery Source", Identifier: "bat1", Label: "电池", Position: "-0.2,0.0,0", Properties: { "电压": VBAT } },
  { ModelID: "Resistor", Identifier: "r1", Label: "电阻", Position: "0.2,0.0,0", Properties: { "电阻": R } },
  { ModelID: "Simple Switch", Identifier: "sw1", Label: "开关", Position: "0.0,0.0,0.15", Properties: { "开关": 1 } },
  { ModelID: "Ground Component", Identifier: "gnd1", Label: "接地", Position: "0.0,0.0,0.3", Properties: {} }
];
const wires = [
  { Source: "bat1", SourcePin: 0, Target: "r1", TargetPin: 0, ColorName: "黑色导线" },
  { Source: "r1", SourcePin: 1, Target: "sw1", TargetPin: 0, ColorName: "黑色导线" },
  { Source: "sw1", SourcePin: 1, Target: "bat1", TargetPin: 1, ColorName: "黑色导线" },
  { Source: "bat1", SourcePin: 1, Target: "gnd1", TargetPin: 0, ColorName: "黑色导线" }
];
const sav = JSON.stringify({ Type: 0, CameraSave: "", StatusSave: JSON.stringify({ Elements: elements, Wires: wires }) });

const p = allocStr(sav);
const ex = M._pl_experiment_load_from_string(p, enc.encode(sav).length);
M._free(p);
if (!ex) { console.log("FAIL load:", err()); process.exit(1); }
console.log("experiment loaded:", ex);

const circ = M._pl_pe_circuit_build(ex);
if (!circ) { console.log("FAIL build:", err()); process.exit(1); }
console.log("circuit built:", circ);

// OP (steady state) suits this purely resistive loop; TR needs set_tr(dt, t_stop).
if (M._pl_pe_circuit_set_analyze_type(circ, 0) !== 0) { console.log("FAIL set_analyze_type:", err()); process.exit(1); }
if (M._pl_pe_circuit_analyze(circ) !== 0) { console.log("FAIL analyze:", err()); process.exit(1); }
console.log("analyze (OP): ok");

// digital clock step (digital part no-op for analog-only circuit, must not crash)
console.log("digital_clk:", M._pl_pe_circuit_digital_clk(circ));

const wb = M._pl_pe_circuit_write_back_to_pl(circ, ex);
if (wb !== 0) { console.log("FAIL write_back:", err()); process.exit(1); }
console.log("write_back: ok");

const dumpPtr = M._pl_experiment_dump(ex, 0);
const dumped = readCStr(dumpPtr);
if (dumpPtr) M._free(dumpPtr);
const root = JSON.parse(dumped);
const status = JSON.parse((root.Experiment || root).StatusSave);
const byId = new Map(status.Elements.map((e) => [e.Identifier, e]));
console.log("--- write-back result ---");
for (const e of status.Elements) console.log(e.Identifier, JSON.stringify(e.Statistics || {}));

// Verify Ohm's law on the loop current. The engine stamps resistive elements as
// conductances (no MNA branch), so per-branch current is exposed on the switch
// and battery; its magnitude must equal V/R.
const iLoop = Math.abs(byId.get("sw1").Statistics["电流"]);
const iExpected = VBAT / R;
const vR = byId.get("r1").Statistics["电压"];
console.log(`loop current |I|=${iLoop} (expect ${iExpected}), resistor U=${vR}`);
if (Math.abs(iLoop - iExpected) > 1e-6) { console.log("FAIL: current != U/R"); process.exit(1); }
if (Math.abs(vR - VBAT) > 1e-6) { console.log("FAIL: resistor voltage != VBAT"); process.exit(1); }

M._pl_pe_circuit_destroy(circ);
M._pl_experiment_destroy(ex);
console.log("SMOKE OK");

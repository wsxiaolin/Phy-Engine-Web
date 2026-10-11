// Phy-Engine WASM smoke test (Node)
// Chain: create experiment -> load .plsave JSON -> build circuit -> analyze
//        -> write back -> dump. Proves the whole engine path works pre-frontend.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const { default: createModule } = await import(join(here, "../build/wasm/phy_engine.js"));

// Node cannot fetch() file URLs — hand the wasm binary over directly.
const Module = await createModule({
  wasmBinary: readFileSync(join(here, "../build/wasm/phy_engine.wasm"))
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
const elements = [
  { ModelID: "Battery Source", Identifier: "bat1", Label: "电池", Position: "-0.2,0.0,0", Properties: { "电压": 3 } },
  { ModelID: "Resistor", Identifier: "r1", Label: "电阻", Position: "0.2,0.0,0", Properties: { "电阻": 100 } },
  { ModelID: "Simple Switch", Identifier: "sw1", Label: "开关", Position: "0.0,0.0,0.15", Properties: { "状态": "闭合" } }
];
const wires = [
  { Source: "bat1", SourcePin: 0, Target: "r1", TargetPin: 0, ColorName: "黑色导线" },
  { Source: "r1", SourcePin: 1, Target: "sw1", TargetPin: 0, ColorName: "黑色导线" },
  { Source: "sw1", SourcePin: 1, Target: "bat1", TargetPin: 1, ColorName: "黑色导线" }
];
const sav = JSON.stringify({ Type: 0, CameraSave: "", StatusSave: JSON.stringify({ Elements: elements, Wires: wires }) });

const p = allocStr(sav);
const ex = M._pl_experiment_load_from_string(p);
M._free(p);
if (!ex) { console.log("FAIL load:", err()); process.exit(1); }
console.log("experiment loaded:", ex);

const circ = M._pl_pe_circuit_build(ex);
if (!circ) { console.log("FAIL build:", err()); process.exit(1); }
console.log("circuit built:", circ);

console.log("set analyze TR:", M._pl_pe_circuit_set_analyze_type(circ, 4)); // TR
console.log("analyze:", M._pl_pe_circuit_analyze(circ));
if (M._pl_pe_circuit_analyze(circ) !== 0) { console.log("analyze err:", err()); }

// digital clock step (digital part no-op for analog-only circuit, must not crash)
console.log("digital_clk:", M._pl_pe_circuit_digital_clk(circ));

const wb = M._pl_pe_circuit_write_back_to_pl(circ, ex);
console.log("write_back:", wb, wb !== 0 ? err() : "");

const dumpPtr = M._pl_experiment_dump(ex, 0);
const dumped = readCStr(dumpPtr);
if (dumpPtr) M._free(dumpPtr);
const stats = JSON.parse(dumped);
const el = stats.StatusSave ? JSON.parse(stats.StatusSave).Elements : stats.Elements;
console.log("--- write-back result ---");
for (const e of el) console.log(e.Identifier, JSON.stringify(e.Statistics || {}));

M._pl_pe_circuit_destroy(circ);
M._pl_experiment_destroy(ex);
console.log("SMOKE OK");

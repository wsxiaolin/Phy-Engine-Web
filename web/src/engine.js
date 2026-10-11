// Thin wrapper around the Phy-Engine WASM build (build/wasm/phy_engine.{js,wasm}).
// Handles string marshalling and the load -> build -> analyze -> write-back path.

let Module = null;

export async function initEngine() {
  if (Module) return Module;
  const url = new URL("/wasm/phy_engine.js", window.location.origin).href;
  const mod = await import(/* @vite-ignore */ url);
  Module = await mod.default({ locateFile: (p) => `/wasm/${p}` });
  return Module;
}

function cstr(s) {
  const bytes = new TextEncoder().encode(s);
  const ptr = Module._malloc(bytes.length + 1);
  Module.HEAPU8.set(bytes, ptr);
  Module.HEAPU8[ptr + bytes.length] = 0;
  return { ptr, len: bytes.length };
}

function readCStr(ptr) {
  if (!ptr) return null;
  let end = ptr;
  while (Module.HEAPU8[end] !== 0) end++;
  return new TextDecoder().decode(Module.HEAPU8.subarray(ptr, end));
}

function lastError() {
  return readCStr(Module._phy_engine_last_error());
}

export class Engine {
  constructor() {
    this.exp = 0;
    this.circuit = 0;
  }

  load(savJson) {
    this.destroy();
    const { ptr, len } = cstr(savJson);
    const h = Module._pl_experiment_load_from_string(ptr, len);
    Module._free(ptr);
    if (!h) throw new Error("load failed: " + lastError());
    this.exp = h;
    return h;
  }

  build() {
    if (!this.exp) throw new Error("no experiment");
    const c = Module._pl_pe_circuit_build(this.exp);
    if (!c) throw new Error("build failed: " + lastError());
    this.circuit = c;
    return c;
  }

  analyze(type = 0) {
    if (!this.circuit) throw new Error("no circuit");
    if (Module._pl_pe_circuit_set_analyze_type(this.circuit, type) !== 0)
      throw new Error("set_analyze_type failed: " + lastError());
    if (type === 4 && Module._pl_pe_circuit_set_tr(this.circuit, 1e-4, 0.01) !== 0)
      throw new Error("set_tr failed: " + lastError());
    if (Module._pl_pe_circuit_analyze(this.circuit) !== 0)
      throw new Error("analyze failed: " + lastError());
  }

  digitalClk() {
    if (this.circuit) Module._pl_pe_circuit_digital_clk(this.circuit);
  }

  syncInputs() {
    if (this.circuit && this.exp) Module._pl_pe_circuit_sync_inputs_from_pl(this.circuit, this.exp);
  }

  writeBack() {
    if (!this.circuit || !this.exp) return;
    if (Module._pl_pe_circuit_write_back_to_pl(this.circuit, this.exp) !== 0)
      throw new Error("write_back failed: " + lastError());
  }

  dump(indent = 0) {
    const p = Module._pl_experiment_dump(this.exp, indent);
    const s = readCStr(p);
    if (p) Module._free(p);
    return s;
  }

  destroy() {
    if (this.circuit) {
      Module._pl_pe_circuit_destroy(this.circuit);
      this.circuit = 0;
    }
    if (this.exp) {
      Module._pl_experiment_destroy(this.exp);
      this.exp = 0;
    }
  }
}

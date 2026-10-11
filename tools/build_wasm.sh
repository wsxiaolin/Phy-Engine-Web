#!/usr/bin/env bash
# Build Phy-Engine to WASM with the FULL C API exported.
# Requirements: emsdk 4.0.22 (em++), ripgrep (rg), node.
# Usage:  EM_CONFIG=... ./tools/build_wasm.sh <engine-repo> [out-dir]
# Default engine repo: ../repo (cloned NetLogo-Mobile/Phy-Engine), out: ../build/wasm
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="${1:-$HERE/../repo}"
OUT_DIR="${2:-$HERE/../build/wasm}"

EMXX="${EMXX:-em++}"
command -v "$EMXX" >/dev/null 2>&1 || { echo "em++ not found; set EMXX=/path/to/em++"; exit 1; }
command -v rg >/dev/null 2>&1 || { echo "rg (ripgrep) required"; exit 1; }

mkdir -p "$OUT_DIR"

# Extract every extern "C" symbol name from dll_main.cpp so new engine APIs
# are exported automatically.
EXPORTS="_malloc,_free,$(rg -o 'extern "C"[^({;]*\b([A-Za-z_]\w*)\s*\(' "$ENGINE_DIR/src/dll_main.cpp" -r '$1' \
  | sort -u | sed 's/^/_/' | paste -sd, -)"
echo "exporting $(echo "$EXPORTS" | tr ',' '\n' | wc -l) symbols"

# NOTE: 上游 dll_main.cpp 的 try 块未按 PHY_ENGINE_ENABLE_EXCEPTIONS 条件编译，
# 传 -fno-exceptions 会报 "cannot use 'try'"。上游修复（给 try 加 #if 守卫）后
# 可恢复 -fno-exceptions -fno-cxx-exceptions -fno-unwind-tables 以减小体积。
"$EMXX" \
  -std=c++23 \
  -O2 \
  -I"$ENGINE_DIR/include" \
  "$ENGINE_DIR/src/dll_main.cpp" \
  -fno-rtti \
  -s MODULARIZE=1 \
  -s EXPORT_ES6=1 \
  -s ENVIRONMENT=web \
  -s ALLOW_MEMORY_GROWTH=1 \
  -s FILESYSTEM=0 \
  -s EXPORTED_RUNTIME_METHODS='["cwrap","getValue","setValue","UTF8ToString","stringToUTF8","lengthBytesUTF8"]' \
  -s EXPORTED_FUNCTIONS="[$EXPORTS]" \
  -o "$OUT_DIR/phy_engine.js"

# Emscripten's updateMemoryViews() doesn't publish typed-array views on Module;
# publish them so JS glue can read engine output buffers directly after growth.
node - "$OUT_DIR/phy_engine.js" <<'NODE'
import { readFileSync, writeFileSync } from "node:fs";
const file = process.argv[2];
let s = readFileSync(file, "utf8");
const needle = "HEAPU64=new BigUint64Array(b)}";
if (s.includes(needle)) {
  const inject =
    "HEAPU64=new BigUint64Array(b);Module.HEAP8=HEAP8;Module.HEAPU8=HEAPU8;Module.HEAP32=HEAP32;" +
    "Module.HEAPU32=HEAPU32;Module.HEAPF32=HEAPF32;Module.HEAPF64=HEAPF64;Module.wasmMemory=wasmMemory}";
  s = s.replace(needle, inject);
  writeFileSync(file, s);
  console.log("patched Module heap views");
} else {
  console.log("NOTE: updateMemoryViews needle not found; check runtime API manually");
}
NODE

echo "built:"
ls -la "$OUT_DIR/phy_engine.js" "$OUT_DIR/phy_engine.wasm"

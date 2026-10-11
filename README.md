# phy-engine-web — 物实电路引擎 Web/WASM 版

> 目标：把组织下的新 C++ 电路引擎 **Phy-Engine** 编译为 **WASM**，配 Three.js 前端，
> 视觉与使用体验对齐 Unity 版 Physics-Lab（`NetLogo-Mobile/Physics-Lab` 2.0 分支，
> 不含社区功能）。**sin 对性能敏感。**

**状态：交接中。资产管线 100% 可用（87 元件 GLB+目录+房间）；WASM 构建成功
（91 符号，1.94MB）；当前阻塞 = 引擎 vendored json.hpp 解析全 discarded（已定位，
见 `docs/HANDOVER.md` §1）。前端未动工，完整计划见 `docs/PLAN.md`。**

## 目录结构

```
phy-engine-web/
├── tools/                    # 资产提取与构建管线（Python/Bash，可直接跑）
│   ├── fbx_binary.py         # 二进制 FBX 7.x 解析器（自研，无依赖）
│   ├── unity_yaml.py         # Unity YAML/prefab/mat 解析 + GUID 映射
│   ├── extract_components.py # 87 个元件 prefab → GLB + catalog.json
│   ├── extract_room.py       # 房间/桌子 房间.FBX → room.glb
│   ├── extract_scene.py      # 灯光/相机粗提取（参考用）
│   ├── build_wasm.sh         # Phy-Engine → WASM（自动导出全部 C API）
│   └── materialize_lfs.py    # Unity 仓库 LFS 指针批量物化（clone 后必跑）
├── build/assets/             # 提取产物（git LFS）
│   ├── catalog.json          # 元件目录：ModelID/中文名/分类/pin/Glb 路径
│   ├── components/*.glb      # 87 个元件模型（含贴图，自包含）
│   └── room.glb              # 房间+桌子（9 模型含贴图）
├── build/wasm/               # phy_engine.js + .wasm（构建产物）
├── repo/                     # Phy-Engine 克隆（.gitignore，不入库）
├── unity/                    # Physics-Lab Unity 克隆（.gitignore，不入库）
├── web/                      # 前端（未动工，架构见 PLAN）
└── docs/                     # 交接文档 / 计划书 / 引擎契约
```

## 快速开始

```bash
# 1. 资产重提取（约 1 分钟，需 PyYAML）
pip install pyyaml && python3 tools/extract_components.py && python3 tools/extract_room.py

# 2. WASM 构建（需 emsdk 4.0.22，见 docs/HANDOVER.md 环境节）
EM_CONFIG=<emsdk>/upstream/emscripten/.emscripten EMXX=<emsdk>/upstream/emscripten/em++ \
  bash tools/build_wasm.sh

# 3. 前端开发（未动工）
cd web && npm i && npm run dev   # 规划中的形态
```

## 引擎契约速览（详见 docs/ENGINE_API.md）

- `pl_experiment_load_from_string(.plsave JSON)` → 实验 handle（**原生兼容 Unity 存档**）
- `pl_pe_circuit_build → set_analyze_type/tr → analyze → write_back_to_pl` 
- 写回：元件 `Statistics.电压/电流/功率`，Logic Output `Properties.状态`
- 元件坐标系：`x_unit=0.16, y_unit=0.08, z_unit=0.1`（element_xyz 网格）

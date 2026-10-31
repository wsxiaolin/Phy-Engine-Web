# 交接文档 — 给下一个 Agent

> ⚠️ **状态已过期（2026-10-31 注记）**：本文 §1「WASM 卡在 vendored json.hpp」与
> §3「前端一行代码都还没写」均为 2026-10-11 的历史记录，两个问题后来都已解决。
> 当前状态、剩余阻塞与最新复验结果**以 `docs/HANDOVER-WEB.md` §0 为准**；
> 里程碑完成度见 `docs/PLAN.md` 头部与本文件 §4–§6 的工程坑（仍然有效）。
> main 直推已获 sin 授权（原 §7「一切交付只走 PR」按 PLAN 的授权更新）。

> 交接时点：2026-10-11。前序 agent（冯诺依曼）完成资产管线与引擎契约梳理后按 sin
> 指令打包交接。**读这个文件能省你一整天踩坑时间。**

## 0. 任务一句话

Phy-Engine（C++23 电路引擎）→ WASM + Three.js 前端，视觉/体验对齐 Unity 版
Physics-Lab（无社区功能）。sin 性能敏感。计划书见 `docs/PLAN.md`，
引擎契约见 `docs/ENGINE_API.md`。**本仓库是私有交接仓，正式交付按 sin 指示走。**

## 1. 交接时点状态（历史快照：M1 完成，M2 曾卡在引擎 bug，已于后续解决）

✅ **可用**：
- `tools/` 全套提取管线（Python，依赖仅 PyYAML + ripgrep）
- `build/assets/catalog.json`：87 元件（ModelID/中文名/分类/pin 表/GLB 文件名）
- `build/assets/components/*.glb`：全部元件模型（真网格+贴图内嵌，150MB 总量）
- `build/assets/room.glb`：房间+桌子（Table001/floor/Room-back/glass/door/Windows...9 模型）
- `build/assets/chips.json`：13 种芯片的 PL pin 约定表（含 8bit 的适配缺口标注）
- `tools/build_wasm.sh`：一键 WASM 构建（自动导出 dll_main.cpp 全部 extern "C"）
- `build/wasm/`：**已构建成功**的 phy_engine.js(29KB)/.wasm(1.94MB)，91 符号全导出
- `tools/smoke_test.mjs`：引擎冒烟测试（Node 直跑，wasmBinary 注入式加载）

🚨 **当前阻塞（交接时已定位，未解决）**：
引擎 load_from_string 对**任何输入**（包括合法的 `{}`）都报
`invalid sav json: parse failed`。已用最小探针复现：**仓库内 vendored 的
`include/phy_engine/phy_lab_wrapper/utility/json.hpp`（nlohmann）在 emscripten
-O2 构建下，无论 JSON_NOEXCEPTION 与否，`json::parse(迭代器对)` 一律返回
discarded**——字符串重载/回调/异常宏都不是变量，vendor 副本本身有问题
（内容损坏或被改过）。**下一步首选**：换上游官方 nlohmann json.hpp 重新
对比（单文件放回 `utility/json.hpp`），或在宿主 g++/clang 上跑同一探针
交叉验证是 vendor 损坏还是 emscripten 优化触发 UB。修好后 `smoke_test.mjs`
应全绿（脚本已把 load→build→analyze→write_back→dump 全链路写好）。

⏳ **未做**：前端一行代码都还没写（`web/` 是空的）。

## 2. 环境（本沙箱实测路径，过期就重装）

- **emsdk 4.0.22**：`/tmp/emsdk`（**tmp 会丢**，重装流程：
  ```bash
  curl -sL https://github.com/emscripten-core/emsdk/archive/refs/tags/4.0.22.tar.gz | tar xz
  cd emsdk-4.0.22 && ./emsdk install 4.0.22   # 355MB 下载+解包，中断就重跑
  ./emsdk activate 4.0.22
  source emsdk_env.sh
  ```
  注意：tarball 解出来是 `install/` 子目录，emsdk 脚本会自动归位；
  自带 `emscripten_config` 里 NODE_JS 是构建机路径，activate 会修正。）
- **git-lfs**：`/usr/local/bin/git-lfs`（3.7.0，Unity 仓库必须）
- **Python**：`python3` + `pip install pyyaml`（pip 有 PEP668 限制就 `pip install --break-system-packages` 或用 venv）
- **node**：v24（系统自带）

## 3. WASM 构建验证记录（交接时点）

```bash
EM_CONFIG=<emsdk>/upstream/emscripten/.emscripten \
EMXX=<emsdk>/upstream/emscripten/em++ \
bash tools/build_wasm.sh    # 产物 build/wasm/phy_engine.js + .wasm
```
- 编译时长 ~6 分钟（单 TU C++23 + Eigen/absl 头），产物 wasm ~5.9MB
- 修复：emscripten 的 `updateMemoryViews()` 不把 typed array 挂到 Module 上，
  build_wasm.sh 里的 node patch 补了 `Module.HEAPU8/HEAPF64/...`（内存增长后自动更新）
- Node smoke test（已跑通）：
  ```js
  const Factory = (await import('./build/wasm/phy_engine.js')).default;
  const M = await Factory();
  const exp = M.cwrap('pl_experiment_create', 'number', []);
  // load_from_string → build → analyze → write_back 全链路见 docs/PLAN.md M2
  ```

## 4. 大坑清单（按杀伤力排序）

### 4.1 Unity 仓库克隆（LFS 三连坑）
1. `git clone` 需要 LFS filter，没装 git-lfs 时 checkout 会**静默失败一半**且
   index 被搞坏（`git ls-files` 返回 0）。先 `git lfs install` 再 clone。
2. 坑：如果已经踩了，`git checkout -f HEAD -- .` + `git lfs pull` 修复；
   个别文件残留指针时跑 `python3 tools/materialize_lfs.py`（从 .git/lfs/objects
   按 oid 手动物化，幂等）。
3. 少量二进制（水塔/天体/特效 FBX）LFS 对象拉不全，不影响电路提取。

### 4.2 工具链文件权限
**Write/Edit 工具创建的文件是 root 属主，Bash（z 用户）改不了。**
改 tools/*.py 必须用 Edit 工具或先 `sudo`-less 方案（cp 到 /tmp 改完再
用 Write 写回）。Python 脚本运行不受影响（只读）。

### 4.3 FBX 解析（tools/fbx_binary.py 的关键约定）
- FBX 对象名带复合后缀：`名字\x00\x01类型`，**必须 split('\x00')[0]**；
  且注意 `Node.name` 是节点类型名（'Model'），**对象显示名在 prop(1)**——
  曾经因为这个 9 个房间模型全变成一个（dict 键全是 'Model' 互相覆盖）
- **Mesh fileID 映射（实证过）**：prefab 里 `m_Mesh: {fileID: 4300000+2i}` 按顺序
  对应 FBX 第 i 个带几何的 Model。Resistor 实证：Pin2→4300000、Pin1→4300002、
  底板→4300004 ✓。名字匹配不可靠（FBX 内部叫 对象016 之类），fileID 才是正道
- UV/法线 mapping 有 AllSame/ByVertice/ByPolygonVertex(+UVIndex) 多种，
  `_emit_mesh` 按角点展开统一处理，别改成"按顶点复用"（硬边会糊）

### 4.4 Unity YAML（tools/unity_yaml.py）
- 文档头 `--- !u!114 &123` 用正则切，body 是 `{类名: {...}}` 包装要解一层
- `z: -1e-15` 这类科学计数法 PyYAML 会解析成**字符串**（YAML 1.1 规范），
  `_num()` 强转兜底——新增字段解析记得过 `_num`
- `m_TexEnvs` 等列表字段 PyYAML 出来是 `[{'_MainTex': {...}}]` 单键 dict 列表，
  用 `_entries()` 归一化，别当 tuple

### 4.5 坐标/单位（错一点全场景歪）
- Unity LH、three RH：**MIRROR_X** 统一换轴——顶点 (−x,y,z)、四元数 (x,−y,−z,w)、
  翻转三角绕序、UV v 翻转。GLB 已做完，前端别再变换
- FBX 单位 cm：×0.01。房间 FBX bbox ±65 是 65cm 不是 65m
- 桌面网格 element_xyz：x 0.16 / y 0.08 / z 0.1（引擎 physicslab.h 权威定义），
  存档 Position 用网格坐标 pack，别用世界坐标

### 4.6 pin 与芯片（最容易接错线的地方）
- **PL pin 序是 wire 索引的权威**（pe_sim.h 特判注释），芯片 outputs-first、
  门电路引擎序，详见 ENGINE_API.md §4.3 表。别按引擎头文件顺序想当然
- 13 种芯片（DFF/加法器/Counter...）prefab 里 Pins=[]，pin 由前端按 §5 公式生成
- 8bit Input/Display 引擎侧未接（M2 待办，改 pe_sim.h 走 PR）

### 4.7 沙箱 Bash 稳定性
- 长命令（>1min）用 `setsid nohup ... &` 后台跑 + 日志轮询，前台跑会被 504 掐断
  （掐断≠失败，进程常还在跑，先查状态再重试，别开重复进程抢锁）
- git 操作留意 index.lock 残留，先 `pgrep -af git` 再 `rm .git/index.lock`

## 5. 关键参考文件（Unity 仓库内，别丢了）

| 看什么 | 路径（相对 unity/） |
|---|---|
| 元件目录与分类顺序 | `Assets/Resources/Experiments/Order.txt`（空行分组=UI tab） |
| 全部元件 prefab | `Assets/Resources/Experiments/{Basic,Analog,Logic,Sequential,Combinational,Instrumentations,Home,Sensors}*/` |
| 元件 3D 模型+贴图 | `Assets/Physics-Lab/Circuits/`（FBX+Textures） |
| 房间桌子 | `Assets/Physics-Lab/Rooms/`（Meshes/房间.FBX、Materials/） |
| 芯片 pin 运行时布局 | `Assets/Scripts/Circuits/Components/Chips/ChipComponent.cs` OnPoolCreating |
| 导线颜色/渲染 | `Assets/Scripts/Interfaces/Dialogs/DialogWires.cs` + `Wires-Pins/WireManager.cs` |
| 存档结构 | `Assets/Scripts/Circuits/CircuitExperiment.cs`（StatusSave 序列化） |
| UI 设计语言 | `Documents/images/*.png`（白卡片、圆角、蓝点缀、Lato 字体） |
| 场景 | `Assets/Circuits/Scenes/Scene Circuits.unity`（91k 行，按需 rg） |

## 6. 接下来按顺序做（对应 PLAN.md 里程碑）

1. **M2 收尾**：Node smoke test 全链路（造一个电池+电阻+开关的 .plsave →
   analyze → write_back → 验证 Statistics.电流=U/R）
2. **M3 场景**：three.js 起 room.glb + 相机。**先拿一个元件渲染对照**
   （VLM 看材质/朝向是否对，GLB 坐标约定错了这步立刻暴露）
3. **M3 交互→M4 连线→M5 仿真**，节奏别反（连线没仿真没反馈没灵魂）
4. 每完成一步：`git commit`（本仓随便提）；**涉及引擎改动的走
   NetLogo-Mobile/Phy-Engine 的 PR，别碰别人 main**
5. 交付给 sin 看之前：VLM 全 PASS + 性能数字（首屏耗时、帧率、analyze 延迟）

## 7. 与 sin 协作注意（前序 agent 的血泪，全文见仓库外记忆）

- **一切交付只走 PR**；sin 明确授权才可碰主线
- **永远不要创建定时任务/cron/自唤醒**（10-01 暴怒铁律，永不过期）
- 汇报要短、列条目、带证据；sin 反馈风格是"列 1-4 条问题+截图，务必全修"
- 他不在场时放权自主迭代，但交付必须"完美可用"才上会

## 8. 本仓库维护约定

- `*.glb` 走 LFS（.gitattributes 已配）；clone 后 `git lfs pull`
- `repo/`（引擎克隆）和 `unity/`（Unity 克隆）不入库（.gitignore），重建步骤：
  ```bash
  GIT_ASKPASS=<脚本回显token> git clone https://github.com/NetLogo-Mobile/Phy-Engine.git repo
  GIT_ASKPASS=... git clone -b 2.0 https://github.com/NetLogo-Mobile/Physics-Lab.git unity && cd unity && git lfs pull && python3 ../tools/materialize_lfs.py
  ```
- GitHub 凭据：sin 的 token 在沙箱 `/home/z/.gh-token-pltown`（wsxiaolin 账号，
  scopes: repo+workflow+gist+read:org），推送用 `GIT_ASKPASS` 方式（见
  tools/gh-askpass.example.sh），**不要把 token 写进任何文件/remote URL**

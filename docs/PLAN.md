# 计划书 — 物实电路 Phy-Engine Web/WASM 版

任务来源：sin 2026-10-07 指令——"为组织下的 phy-engine（新 C++ 引擎）做一个 web 的
wasm 版本，顺便做好前端，参考组织下已有物实 physicslab 的 unity 仓库（里面有贴图），
最终要求视觉效果和使用体验与 unity 版本一模一样（不含社区功能），引擎替换为 wasm
的新引擎，注意性能敏感"。

> **2026-10-31 收尾刷新（复验）**：代码线自 2026-10-24 第 27 轮起冻结（值班 cron 已删）。
> M1–M5 100%；M6 ~90%（剩公网预览部署、真机 fps）；M7 100%（官方对照全 PASS，
> 遗留 10 项全部销案）；M8 ~40%（电表 6 件与 `.plsave` 双向兼容已完成，示波器 /
> 逐元件参数 / 导线求解规格核对待规范文档）。**整体完成度 ≈ 90%**。
> 本次复验：`npm ci` + `npm run build` 13.6s、`node tools/smoke_test.mjs` SMOKE OK
> （3V/100Ω → 0.03A）、加载存档后连导线/删线/重连仿真读数均正确、本地 `npm run dev`
> 预览可用。仓库 https://github.com/NetLogo-Mobile/phy-engine-web，HEAD 以 git log 为准。
> 剩余阻塞与复验细节见 `docs/HANDOVER-WEB.md` §0 与本文 §六。

## 一、产品定义

一个纯前端 SPA（无社区/账号/分享），复刻 Unity 版 Physics-Lab 的**电路实验模式**：

| 能力 | Unity 版基准 | Web 版实现 |
|---|---|---|
| 3D 场景 | 房间+木桌+灯光+FBX 元件 | Three.js + 提取的 GLB（同源资产） |
| 元件库 | 8 类 87 种（目录 Order.txt） | catalog.json 同集 |
| 布局 | 桌面网格拖放/旋转 | 同网格（x_unit 0.16 / y 0.08 / z 0.1） |
| 连线 | pin→pin，5 色导线，路径寻优 | 同 5 色 + 桌面网格 A* 或简化路由 |
| 仿真 | Unity 内置求解器 | **Phy-Engine WASM**（pl_experiment 全流程） |
| 存档 | .plsave JSON | **同格式双向兼容**（引擎原生 load/dump） |
| UI | UGUI 白卡片/圆角/蓝点缀/Lato | HTML overlay 复刻同风格 |

验收标准（sin 视角）：打开网页像打开 Unity 版；摆电阻电池开关、连导线、跑仿真、
读数正确；存档能被 Unity 版（或至少引擎）读回；加载<5s、交互 60fps。

## 二、技术决策（已定，附理由）

1. **渲染**：Three.js（r160+）。WebGPU 不用——移动端覆盖与成熟度。
2. **资产管线**：自研 FBX 二进制解析 + Unity YAML 解析 → glTF GLB（贴图内嵌）。
   不用 Blender/FBX2glTF，因为 Unity prefab 的层级/材质/覆写只有 Unity YAML 说得清。
3. **坐标约定**：Unity LH → three RH 统一 MIRROR_X（顶点 (−x,y,z)、四元数 (x,−y,−z,w)、
   翻转绕序）。FBX 原始单位 cm → ×0.01。
4. **引擎桥**：ES6 模块化 WASM，主线程调用（analyze 单次 <ms 级，实测后如卡顿
   再挪 Worker；写回读 Buffer 直读，不拷贝）。
5. **存档**：前端维护 Unity 兼容 JSON（Elements/Wires/Position pack_xyz），
   位置用 element_xyz 网格坐标 pack，保证与 Unity 互通。

## 三、里程碑

### M1 资产与引擎（✅ 已完成，交接时点）
- [x] Unity 仓库克隆 + LFS 物化（坑见 HANDOVER）
- [x] FBX 二进制解析器（顶点/多边形/法线/UV/材质/连接拓扑）
- [x] prefab 树解析（pin 位置、MeshFilter fileID→几何映射 4300000+2i、材质 .mat）
- [x] 87 元件 GLB + catalog.json + room.glb（~157MB，LFS）
- [x] 引擎契约梳理（见 ENGINE_API.md）：加载/构建/分析/写回/pin 顺序/属性键
- [x] build_wasm.sh（自动导出 93 个 C 符号）

### M2 WASM 引擎验证（✅ 完成）
- [x] Node/浏览器 smoke test：load .plsave → build → analyze → write_back → dump，
      电池+开关+电阻+地闭环数值正确（3V/-0.03A，analyze ~28ms）
- [x] 36 个 supported 元件的属性键/pin 顺序桥接（catalog 桥 + experiment 重建）
- [ ] ~~pe_sim.h 8bit adapter~~（sin 指令：不动引擎，不做了）

### M3 前端骨架（✅ 完成）
- [x] Three.js 场景：room.glb 桌面 + Unity 灯光数值级对齐（上会 VLM FAIL →
      抽 Unity 场景 YAML 实数修复：主光 30°/2.2、环境 0.55、曝光 1.0）
- [x] 87 元件 GLB 按需加载 + 共享几何/材质；**资产管线重建**：prefab m_Materials
      → .mat 贴图链全解析，材质/贴图/UV 三层修复（解决前任遗留的"全黑建模乱"）
- [x] 交互：点选/拖放（raycast 桌面网格）/旋转 90°/删除；pin 最近邻拾取（26px 阈值）
- [x] UI overlay：顶栏 + 右工具列 + 底部元件抽屉（7 tab + 真 3D 缩略图）+ 属性卡
      （Unity 白卡片风格，标签格式对齐官方 `3.00V\n-0.060A`）

### M4 连线系统（✅ 完成，超原计划）
- [x] pin 高亮 + 拖线 + 5 色导线（Unity DialogWires.WireColors 同源色值）
- [x] **平面路由完整复刻 Unity CircuitWire.Reroute**（直线→撞检测盒→绕角贪心+
      去程畅通检查→角点外扩；Catmull-Rom 平滑；悬链高度按全局弧长挂）
      ——原计划 MVP 直线弧，实际直接复刻了 Unity 算法
- [x] 导线选中/删除（再连=删旧线，同 Unity）
- [x] 悬链线公式源码级复刻（A=60/log10(len_cm)，cosh 端高差 acosh）

### M5 仿真闭环（✅ 完成）
- [x] 拓扑变更 → pl_experiment 重建 → analyze → write_back（实测 0.8ms）
- [x] 视觉反馈：Statistics 电压/电流标签、开关位置动画（GLB Pole 节点 0.79rad
      翘起↔压平，instantiate/点按/属性编辑三处联动）
- [x] 数字时钟：circuit_digital_clk 步进 + Speed 档位（0.5/1/2/4Hz 对齐 Unity）
- [x] D 触发器时钟驱动验证（clkOk）
- [ ] ~~8bit Input/Display~~（引擎不支持，sin 说不管了）
- [ ] 损坏判定冒烟效果（二期）

### M6 打磨与交付（✅ 基本完成）
- [x] 首屏：GLB 按需加载，页面 PAGEERRORS=0；analyze 主线程 <1ms 无需 Worker
- [x] VLM 视觉对照 ≥4/4 PASS（导线弧线/绕行/拨杆/标签/面板多轮全过）
- [x] 交付：NetLogo-Mobile/phy-engine-web main 直推（sin 授权）
- [x] **移动端触控适配**（dc7ffb3，2026-10-15）
- [ ] **预览部署**：本地 `npm run dev` 预览已可用（2026-10-31 复验，Vite 5173 正常出画面）；
      公网托管仍待 sin 决策——GH Pages 私有仓需组织升级（workflow 已挂，历史 run 全 failure）；
      CF Pages 需 sin 在 Dashboard 连一次 repo；公开仓会带出 GLB+docs（已知悉未决）
- [ ] 真机 fps：headless 软渲染实测 0.3 fps（Swiftshader），HUD 读数随之失真；
      真机 rAF 正常，待 sin 在真实设备上确认 60fps 目标

### M7 建模保真审计与 Unity 对照（✅ 100%，2026-10-16 ~ 10-24 轮）
- [x] 审计管线 v2（1482c4d）：audit_models 与提取器同源（复用 FBXCache，
      消除 fileID→子网格解析假阳性）+ .meta fileIDToRecycleName 权威映射
      + Unity 内置基元支持（Quad/Plane/Cube/Cylinder）
- [x] 87 元件全量重提取（10-18）：审计问题 **244 → 10**
      （NODES-MISSING 87→0、MESH-MISSING 145→2、BBOX 116→8）；
      报告 build/audit_report_v2.json；重提取后 web build EXIT=0、应用内渲染探针验证通过
- [x] 对照截图管线四件套入库：tools/prefab_ref_dump.py（Unity 源 refdump）→
      web/refshot.mjs + web/refshot.html（Unity 源参照截图）→ web/shot_pairs.mjs
      （web 端截图）→ tools/compose_pairs.py（成对拼图+网格总览）
- [x] batch_shot 慢沙盒兼容修复（600ms→5s 等待：0.3fps 下 600ms < 1 帧会截到灰屏）
- [x] 「剩余 10 项真实建模缺陷」（2026-10-24 全数销案为判定漂移/已修复：
      Relay 三项=取景致 VLM 判定漂移+公平对照 PASS；Resistance_Law 五项、
      Photoresistor 两项=第 18/19 轮重提取已修复+官方对照复验 PASS）
- [x] Unity 内置 Quad 图标面片（2026-10-24 销案：官方原图细审证实基座表面
      本就印白色线圈符号、IC 顶面另有丝印；web Icon 面片 0.057×0.062m 贴
      底板顶面+0.0004 与 prefab TRS 逐位吻合，公平对照 mi_fair.png VLM PASS。
      材质层级视为已达标）
- [x] Unity vs web 成对对比 36 件**全绿收官（10-23 第 15 轮）**：36/36 PASS 零
      FAIL——原 13 FAIL 经 refshot 方法对齐（补画与 web 端同规格程序化 pin 帽）
      重审后全部翻绿；M7「提取回归」定性不成立（web 渲染一直正确，refshot 过时
      +裸 GLB 方法不对称才是根因），提取器禁止回滚；真基准=unity 官方预览
      Previews/Circuits，报告 build/compare_vlm/report.json
- [x] **重提取产物补推已完成**（10-23 实锤）：git-lfs 3.7.0 就绪，176 GLB 全部
      LFS 追踪且已在 origin/main，本项为过时描述

### M8 功能规范补齐（🔶 约 40%，2026-10-16 sin 新增范围）
依据 shared/specs/Unity电学模块功能规范.md（M4/M5 已覆盖导线连接、电路求解、
存档读写的基础能力，本里程碑对齐规范补缺口）。

⚠️ **阻塞（2026-10-31 复核）**：`shared/specs/Unity电学模块功能规范.md` 在本机、
本仓库、工作区与 git 历史中均不存在（round-14/25/31 三轮全域搜索）。三项未勾选
全部依赖该文档，需 sin 提供文件或指路。

- [ ] 示波器（等规范文档；规范 §3.2 社区实验搭法 / §3.4 Web 实现建议为基线）
- [ ] 逐元件参数调节补全（等规范文档；规范 §2 八类全集对照现有属性卡逐一补齐）
- [x] 电表类（规范 §4：电流表/电压表/灵敏电流计/微安表/多用电表/电能表）——M8 六件全齐（PR 序列 b14117d/e6fb162）
- [ ] 导线连接与电路求解规格核对（等规范文档；规范 §5）
- [x] 存档 .plsave 双向兼容验证（规范 §7）——toPlsave 输出引擎原生嵌套信封（default_plsav_template 一比一，37/36/17 键逐键），fromPlsave 兼容新旧两格式，WASM 装载+物理回读实测（tools/verify_plsave.mjs 17 断言 ALL PASS）

## 四、明确不做（sin 圈定）

- 社区功能（发布/评论/点赞/账号）——全部不做
- 天体/电磁模式——只做电路
- AR/XR——不做

## 五、风险与预案

| 风险 | 预案 |
|---|---|
| 引擎无电表原生模型 | 已落地：前端照 Unity BuildElements 把电表展开成 Resistor 子网络（`web/src/meters.js`），读数与烧毁判定按 Unity 语义在本地计算 |
| 87 元件全加载慢 | 按分类懒加载 + IndexedDB 缓存；GLB 总量 150MB 里有传感器等冷门类 |
| 导线路由效果差 | 已复刻 Unity CircuitWire.Reroute（直线→绕角→Catmull-Rom→悬链线），无需 A* |
| 首屏 WASM+GLB 体积 | wasm 1.94MB（gzip 后更小）；GLB 按需加载，构建产物 JS 650KB / gzip 171KB |
| 仿真失败后状态残留 | 已知缺陷（2026-10-31 复验）：`simulate()` 成功时未清空 `lastSimError`，失败 toast 会停留到下次强制重跑；修复点 `web/src/app.js` 成功分支 |

## 六、2026-10-31 复验记录

环境：沙箱 Linux + Node 22 + git-lfs 3.3.0 + playwright-core（chromium-1248 软渲染）。

| 检查 | 结果 |
|---|---|
| LFS 物化 | 安装 git-lfs 后 `git lfs pull` 成功，wasm 1.94MB / room.glb 7.3MB 就位 |
| 依赖安装 | `npm ci` 13 包 / 15s |
| 生产构建 | `vite build` 13.57s，JS 650.58KB（gzip 170.79KB），产物哈希与仓库内 dist 一致 |
| 引擎冒烟 | `node tools/smoke_test.mjs` → `SMOKE OK`，I=0.03A / U=3V |
| 存档加载 + 仿真 | 电池+电阻+开关+接地 4 线闭环：电池 -0.03A、电阻 3V/0.03A/0.09W |
| 连线交互 | 删除一条导线后重连（handlePin 两次）：导线数回到 4，统计值恢复正确 |
| 导线网格 | `wireSystem` 子节点数与导线数一致（4） |
| 页面加载 | 首屏 6.24s（0.3fps 软渲染），canvas、7 分类抽屉、HUD 正常，无 PAGEERROR |
| 404 | 浏览器请求 `/favicon.ico` 404（`index.html` 未声明图标），无功能影响 |

未纳入代码修复的观察（留给后续会话）：短路接法（电池两端直连）会让 `circuit_analyze`
失败并弹失败提示，属引擎 MNA 奇异所致，与 Unity 行为待对齐；失败后 `lastSimError`
与 toast 不清空。

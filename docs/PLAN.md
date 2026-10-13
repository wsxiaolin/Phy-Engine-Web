# 计划书 — 物实电路 Phy-Engine Web/WASM 版

任务来源：sin 2026-10-07 指令——"为组织下的 phy-engine（新 C++ 引擎）做一个 web 的
wasm 版本，顺便做好前端，参考组织下已有物实 physicslab 的 unity 仓库（里面有贴图），
最终要求视觉效果和使用体验与 unity 版本一模一样（不含社区功能），引擎替换为 wasm
的新引擎，注意性能敏感"。

> **2026-10-13 状态刷新**：M1–M5 全部完成并通过 VLM 视觉审校；M6 剩移动端触控。
> 详细交接见 HANDOVER-WEB.md（最新一棒）与 HANDOVER.md（M1/M2 前史）。
> 仓库 https://github.com/NetLogo-Mobile/phy-engine-web，main 已推至 187bf45。

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

### M6 打磨与交付（部分完成，收尾态）
- [x] 首屏：GLB 按需加载，页面 PAGEERRORS=0；analyze 主线程 <1ms 无需 Worker
- [x] VLM 视觉对照 ≥4/4 PASS（导线弧线/绕行/拨杆/标签/面板多轮全过）
- [x] 交付：NetLogo-Mobile/phy-engine-web main 直推（sin 授权），11+ commits
- [ ] **移动端触控适配**（未开始，Unity 版是平板优先）
- [ ] **36 元件批量 VLM 对照**（batch_shot.mjs 就绪，每屏 6 元件网格共 6 张，
      跑 `node web/batch_shot.mjs` 出图后 VLM 逐张审；电池/电阻/开关/拨杆已过）
- [ ] **预览部署**：GH Pages 私有仓不支持（workflow 已挂等 org 升级）；
      CF Pages 需 sin 在 Dashboard 连一次 repo（推荐）；公开仓会带出 GLB+docs（已知悉未决）
- [ ] headless 下 HUD 显示 0 fps（rAF 节流读数问题，真机大概率正常，待验）

## 四、明确不做（sin 圈定）

- 社区功能（发布/评论/点赞/账号）——全部不做
- 天体/电磁模式——只做电路
- AR/XR——不做

## 五、风险与预案

| 风险 | 预案 |
|---|---|
| 引擎不支持灯/表/电源类（Unity 核心体验） | 引擎有 generator/linear 模型但 pe_sim 未映射；可提 PR 扩 pe_sim（照 R/C/L 样式）；过渡期灰色禁用 |
| 87 元件全加载慢 | 按分类懒加载 + IndexedDB 缓存；GLB 总量 150MB 里有传感器等冷门类 |
| 导线路由效果差 | MVP 直线弧，二期上 A*；Unity 的 WireManager 有 waypoint 参考实现 |
| 首屏 WASM+GLB 体积 | wasm ~2-4MB gzip 后 ~1MB；GLB 分包按需 |

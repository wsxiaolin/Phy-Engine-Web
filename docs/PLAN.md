# 计划书 — 物实电路 Phy-Engine Web/WASM 版

任务来源：sin 2026-10-07 指令——"为组织下的 phy-engine（新 C++ 引擎）做一个 web 的
wasm 版本，顺便做好前端，参考组织下已有物实 physicslab 的 unity 仓库（里面有贴图），
最终要求视觉效果和使用体验与 unity 版本一模一样（不含社区功能），引擎替换为 wasm
的新引擎，注意性能敏感"。

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

### M2 WASM 引擎验证（进行中）
- [ ] 构建产物在 Node/浏览器 smoke test：load 示例 .plsave → build → analyze →
      write_back → dump，数值合理（电阻分压等）
- [ ] 补 pe_sim.h：8bit Input/Display 的 adapter 展开（引擎模型已存在
      eight_bit_input.h/display.h，pin b7..b0，只差 pin_map 接线；走 PR）
- [ ] 性能基线：大电路（50+ 元件）analyze 耗时记录

### M3 前端骨架
- [ ] Three.js 场景：room.glb 桌面 + 灯光（暖主光 1.2 + 补光）+ 相机（Unity 桌面视角）
- [ ] 元件实例化：GLB 按需加载 + 共享几何/材质缓存（性能：draw call 合批评估）
- [ ] 交互：点选/拖放（raycast 桌面网格）/旋转 90°/删除；框选可选
- [ ] UI overlay：顶栏（返回/保存/加载/仿真开关）、右侧操作条、元件库抽屉
      （分类 tab：基础电路/模拟电路/逻辑电路/时序逻辑/组合逻辑/仪表）、
      属性对话框（双击元件， Unity 白卡片风格）

### M4 连线系统
- [ ] pin 高亮 + 拖线预览（bezier/bundle 管状线）
- [ ] 5 色导线（黑/蓝/红/绿/黄，Unity DialogWires.WireColors）+ 色选弹窗
- [ ] 桌面平面路由（Unity 用 waypoint 网格 A*，MVP 可先直线+抬升弧线）
- [ ] 导线选中/删除

### M5 仿真闭环
- [ ] 拓扑变更 → pl_experiment 重建 circuit → analyze → write_back
- [ ] 视觉反馈：Statistics 电压/电流显示（元件上方 HTML 标签或纹理）、
      Logic Output 状态色、开关位置动画
- [ ] 数字时钟驱动：circuit_digital_clk 步进 + 速度控制（Unity Speed 档位）
- [ ] 8bit Input 面板交互（8 开关）、8bit Display 点阵显示
- [ ] 损坏判定（短路→IsBroken 冒烟效果，二期）

### M6 打磨与交付
- [ ] 性能：首屏 <5s（GLB 逐个按需 + 总量压缩评估 meshopt）；稳态 60fps
- [ ] VLM 视觉对照（截图 vs Unity 风格基准）≥ 4/4 PASS
- [ ] 交付：NetLogo-Mobile 私有仓库 PR（或按 sin 指示新仓库直接推）
- [ ] 移动端触控适配（Unity 版是平板优先交互）

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

# 交接文档 — Web 前端（2026-10-13 定稿）

> 本文档取代 2026-10-11 版（图灵棒）。M1/M2 前史见 HANDOVER.md，工程契约见 ENGINE_API.md。
> **本文描述与 main@187bf45 一致。接手前先 `git pull`。**

## 0. 一句话现状

Unity Physics-Lab 电路模式的 Web 复刻**已可用**：87 元件摆放/旋转/属性、5 色导线
（含 Unity 同款绕障路由+悬链下垂）、WASM 实时仿真（analyze <1ms）、数字时钟、
开关拨杆动画。sin 指令「不做新功能了」，剩余项全是打磨与部署。

## 1. 环境与常用命令

| 事项 | 值 |
|---|---|
| 仓库 | https://github.com/NetLogo-Mobile/phy-engine-web（私有） |
| 推送凭据 | GIT_ASKPASS=/tmp/gh-askpass.sh（token 在 /home/z/.gh-token-pltown，若失效找 sin 重发） |
| web 构建 | `cd web && npm run build`（产物 build/→web/dist/，构建后 **必须** `cp ../build/assets/*.json web/dist/assets/`，catalog/chips 是运行期读的） |
| 本地起服务 | 任意静态服务器指 web/dist（例：itest.mjs 内置 8937，batch_shot.mjs 用 8951；**5173 被 pl-town 占**） |
| 场景级 e2e | `cd web && node itest.mjs`：摆电池/电阻/开关/地+连线+toggle+属性改值+切时钟，输出 JSON 断言 + build/interact_final.png，PAGEERRORS 必须 0 |
| 批量元件截图 | `cd web && node batch_shot.mjs` → build/grid_N.png（36 supported 元件，每屏 6 个） |
| WASM 重建 | `./build_wasm.sh`（只有改引擎 C++ 才需要；sin 圈定不动引擎） |
| 资产重提 | `python3 tools/extract_components.py`（只有改提取逻辑才跑，~分钟级） |

## 2. 各系统现状与实现要点（接手必读）

### 2.1 资产管线（tools/）
- 87 元件 GLB = 自研 FBX 二进制解析 + **prefab m_Materials → .mat 贴图链**。
  10-11 版重建后材质/贴图/UV 全对（前任的"全黑建模乱"已根治，勿回退旧提取逻辑，
  坑见 HANDOVER.md §4.3：UV 有 AllSame/ByVertice/ByPolygonVertex 三种映射）。
- catalog.json：ModelID/FriendlyName/pins（位置+isPositive）/属性默认值/glB 路径。
  **pins 坐标与 GLB 网格矩阵精确一致**——这是"导线能扣上接线柱"的根基，改动需全量回归。

### 2.2 坐标约定（全局铁律）
- Unity LH → three RH：顶点 (−x,y,z)、四元数 (x,−y,−z,w)、翻转绕序（MIRROR_X）。
- FBX 单位 cm ×0.01；桌面 TABLE_Y=0.78。
- **一比一复刻纪律**：外观/物理参数必须从 Unity 源文件抽数值（场景 YAML/prefab/C#），
  禁止凭感觉写。两次教训：灯光凭感觉 VLM FAIL（抽 YAML 实数后 PASS）；悬链 A 参数
  凭感觉把下垂当振幅（扎进桌面渲染成扇形，抽源码 cosh 公式后修复）。

### 2.3 WASM 引擎桥（src/engine.js）
- pl_experiment 全流程：add/remove element/wire → build → analyze → write_back → dump。
- 仿真触发：任何拓扑/属性变更 `scheduleSimulate()`（防抖），实测单次 0.8ms，主线程够用。
- supported 元件清单与 catalog.js SUPPORTED 集合一致（36 个）；引擎没有的元件
  （灯泡/仪表/传感器）只摆放不仿真——sin 圈定「不管了」，勿扩引擎。

### 2.4 导线系统（src/wires.js）——本棒核心交付
- 平面路由：`routeWire2D()` 复刻 Unity CircuitWire.Reroute——直线→撞元件检测盒
  （xz AABB 外扩 8mm）→绕角贪心（**去程畅通检查**防对角穿越，Unity 无此项但必需）→
  角点外扩 4mm。障碍=除导线两端元件外的所有元件。
- 平滑：Catmull-Rom（Unity 自然样条的近似），每段插值 `clamp(round(len²/0.02),3,10)`。
- 悬链高度：`catenaryY()` 照抄 Render()——A=60/log10(len_cm)，
  y(t)=(B+cosh(lerp(Hs,He,t)))/A，端高差 acosh 展开；**按全局弧长参数挂**，与平面路由解耦。
- 单测：`node route_test.mjs`（直连/单盒/双盒斜穿/反向 4 场景）。
- 已知取舍：检测盒外扩+角点外扩是「Unity 缩小碰撞盒+侧别惩罚」的等效实现，
  视觉验收通过；如后续要更贴 Unity，补 JudgeCollinear 侧别价格即可。

### 2.5 交互契约（src/app.js）
- pin 拾取：屏幕空间最近邻（26px×FoV 系数），别改成 3D raycast——pin 模型太小。
- 点击语义：点元件=选中+属性卡；选中后点 pin=开始/完成连线；同 pin 再点=取消；
  已有导线的两 pin 再连=**删除旧线**（同 Unity）。
- 开关拨杆：GLTFLoader 后节点名 `Pole`（注意**下划线**版本是父节点 Switch_Pole），
  原始 rotation.x=0.79=翘起断开位，闭合压平到 0；`syncPole()` 在 instantiate/
  toggleInteractive/属性 onChange 三处联动。**其他元件如有可动件，同样找 GLB 节点名**。
- 数字时钟：circuit_digital_clk 步进，Speed 档 0.5/1/2/4Hz 对齐 Unity。

### 2.6 UI（src/ui.js + index.html）
- 顶栏 + 左工具列（返回/连线）+ 右工具列（⏸/速度/＋）+ 底部元件抽屉（7 官方 tab、
  真 3D 缩略图 thumbnail() 离屏渲染）+ 属性卡（白卡片）。
- 标签格式 `3.00V\n-0.060A` 对齐官方。相机 FoV30/pitch50/距离 1.4 对齐 CircuitCamera。

## 3. 验证基线（改完代码必须全绿）

1. `npm run build` 无 error（rollup warning 忽略）
2. `node route_test.mjs` 4 PASS
3. `node itest.mjs`：simOk/swToggle/clkOk 全 true，PAGEERRORS: 0
4. 截图 VLM 审（z-ai vision，提示词模板见 git log 各 commit）：不穿模/弧线自然/
   端点扣合/面板正常，≥4/4 PASS 才准推

## 4. 遗留与建议顺序

1. **36 元件批量 VLM 对照**：batch_shot.mjs 就绪（catalog 读取已修正，跑一次出 6 张
   网格图）。重点看：门类芯片丝印方向、仪表表盘、传感器造型与官方预览图差异。
   （上次会话因平台网关故障未跑成，脚本本身没验证过——首跑可能要小修）
2. **预览部署**：CF Pages 需 sin 在 Dashboard 连 repo（Build command
   `cd web && npm run build`，输出 web/dist）；GH Pages 等 org 升级；公开仓方案
   会带出 GLB 资产与 docs/，sin 已知悉未决。
3. **移动端触控**：pointer events 大体兼容，重点补双指缩放（controls.enableZoom
   冲突）与抽屉滑动手势。Unity 版是平板优先，这是 sin 圈定的最后功能项。
4. **headless 0 fps**：HUD 读数在无头浏览器为 0（rAF 节流），真机待验；如是 bug
   查 scene.js 帧计数。
5. **暂停/恢复期间 GLB 缓存**：87 个 GLB ~157MB，IndexedDB 缓存是 PLAN.md 里的
   备选（当前按需加载已够快，非必须）。

## 5. 不要做的事（sin 明确）

- 不动引擎 C++（pe_sim 缺口=灯/表/电源/8bit，一律不补）
- 不做社区功能/天体电磁/AR
- 不碰 main 保护规则以外的东西；推送走 main（sin 已授权直推，但 CI 必须绿）

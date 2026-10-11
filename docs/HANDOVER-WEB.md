# 交接文档 — Web 前端阶段（2026-10-11 晚）

> 前序 agent（图灵）完成：UI 视觉重构对齐 Unity Physics-Lab + 交互契约复刻 + 仿真闭环修复。
> 本文档是给下一个 agent 的完整交接。**M1/M2 见 HANDOVER.md，本文只讲 web/ 与最新结论。**

## 0. sin 的最新指令（2026-10-11）
1. **不要动引擎**（Phy-Engine 不改），引擎不支持的原件"就不管了"。
2. 要复刻"和 Unity 一模一样"的体验，现在差别还很大——**这是总目标**。
3. sin 的原话痛点：建模是乱的、导线连不上、使用体验和 Unity 不一样、没法真实运行仿真。
   其中"导线连不上"和"没法仿真"已修（见 §2），“建模乱”已定位未修（见 §3，**最优先**）。

## 1. web/ 现状（全部已提交）

- Vite + three 0.169，`npm run dev` 落在 **5174**（5173 被 pl-town 占）。`npm run build` 通过。
- UI 壳已按 Unity 参考截图重做：左工具列（返回/AR/连线）、右工具列（⏸/速度/⋯/＋）、
  底部元件抽屉（7 个官方 tab + 真 3D 缩略图，`components.js::thumbnail()` 离屏渲染）、
  左下木质摇杆（相机 orbit）。含 HUD fps/首屏。
- 相机已对齐 Unity CircuitCamera oblique45：**FoV 30°、pitch 50°、距离 1.4、
  中心 (0, TABLE_Y+0.3, -0.45)**（scene.js 内有注释和推导）。
- 交互已按 Unity 契约复刻（研究报告来源见 §4）：
  - **pin 屏幕空间最近邻判定**（app.js::pickPin，阈值 26px×FoV 系数）——解决"导线连不上"。
  - 点击语义：点元件=选中+开属性卡；已选中再点 pin=开始/完成连线；
    同 pin 再点=取消；两 pin 已有导线再连=**删除旧线**。
  - 滚轮 30° 旋转步进（rotateBy）、右键 90°、无网格吸附（Unity 无吸附，SNAP=0）。
  - ⏸ 按钮首次按=运行仿真，之后=暂停/继续。
  - 导线悬链线下垂（wires.js，A=60/log10(len×100) 近似）。
  - 仿真失败会 toast 提示"检查电路是否闭合/接地"。
- 验证过的闭环（probe4）：电池+开关+电阻+地 → 电池 3V/-0.03A、电阻 -3V，analyze ~28ms。
  截图 /tmp/ui_sim.png。

## 2. ⚠️ 已定位未修（下一个 agent 最优先）

### 2.1 资产材质/贴图错乱（"建模乱"的根源）
- 现象：元件几乎全黑、无细节（电池没有电池盒/红黑接线柱质感，灯泡不透明）。
- 已排查的事实：
  - GLB 网格**齐全**（电池 5 mesh：底板/Pin1/Pin2/Battery/容器；位置尺寸对）。
  - 材质数量也对（Battery→speaker skin 贴图 Battery.jpg；其余→Electro05）。
  - **问题在贴图/UV**：Electro05 贴图渲染出来是暗黑塑料，所有 Electro05 材质件
    （底板、pin、容器）都糊成一片。怀疑二选一：
    a) `tools/extract_components.py` 提取材质贴图时**UV 坐标错**（fbx_binary.py 的
       UV mapping 有 AllSame/ByVertice/ByPolygonVertex(+UVIndex) 多种，`_emit_mesh`
       按角点展开处理——HANDOVER §4.3 警告过别乱改，但可能本来就有 bug）；
    b) 贴图**对象选错**（FBX 里 Texture→Video 节点解析，可能拿了同名不同图）。
  - 排查建议：`python3` 里用 `tools/fbx_binary.py::parse()` 读
    `unity/Assets/Physics-Lab/Circuits/电池.FBX`，列出 Texture/Video 节点和每个
    Geometry 用的材质→贴图链；再把 GLB 里的 image dump 出来肉眼比对
    （`/tmp/lamp_img0.png` 是之前 dump 的灯泡贴图，本身像 Electro05 暗色图集——
    但 Unity 里灯泡应该有很多种材质！**6 个材质全指向同一张贴图**这点非常可疑，
    大概率是提取时把 prefab 的材质覆写（m_Materials → .mat 文件）丢了，
    全部 fallback 到 FBX 自带材质）。
  - **关键线索**：Battery Source.prefab 里 Battery 用的是 `speaker skin.mat`
    （含 Battery.jpg 贴图），而 prefab 材质是 Unity 侧覆写。其他元件同理——
    **必须读 prefab 的 m_Materials（guid→.mat 文件），提取 .mat 的贴图引用**，
    而不是用 FBX 内嵌材质。当前代码很可能就是漏了这一步。
- 修好后重新跑 `tools/extract_components.py` 重新生成 87 个 GLB。

### 2.2 引擎不支持元件的仿真回退
- 灯泡/各类表不受引擎支持，放进电路会导致 analyze 失败（`isSupported` 过滤
  已保证 supported 元件子集仿真，但 unsupported 元件接入会断开回路）。
- sin 说"没有的原件就不管了"——保留现状即可，但可以考虑：unsupported 元件
  在连线时当"导通线"处理（Unity 里灯泡是电阻，这里无法模拟，别硬来）。

### 2.3 setPointerCapture 合成事件报错
- 仅测试环境（dispatchEvent 无 pointerId）会报，真机无碍。若要修：try/catch 包住。

## 3. 下一步（按优先级）
1. **修材质提取**（§2.1）——这是"和 Unity 一模一样"的最大短板。
2. 导线避障 waypoint（Unity CircuitWire 有贪心 2D 绕障，MVP 直线弧可先用）。
3. 属性面板做成 Unity 白卡片 metadata 风格（当前是简陋 inspector）。
4. 数字元件时钟驱动（engine digitalClk 已接，UI 无入口）。
5. 性能：首屏 ~4.5s（软件渲染下），真机待测；缩略图懒生成可再优化。

## 4. Unity 交互契约研究报告（复刻依据）
- 完整报告已在上一轮会话产出，关键数值再摘录（文件在 unity/Assets/Scripts/）：
  - WireManager.TryLocatePin：屏幕空间最近 pin，阈值 DPI/13×FoV 系数 ≈12px。
  - CircuitWire：宽 0.005m，曲率 0.02，悬链 A=60/log10(长×100)，避障 waypoint 上限 100，
    电子流间距 0.02m、速度 10（选中元件才显示）。
  - CircuitComponent：点击位移<32px 才算点击；滚轮 30° 旋转；双指旋转 90° 吸附。
  - CircuitCamera：FoV 30（微距 16.5+d×45）；斜视 pitch50 dist1.4 中心+0.3Y/-0.45Z；
    俯视 pitch90 dist2；平移中心钳 [-1,1]；拖拽 Δ=pointerDelta×(1080/宽)，
    pitch += Δy×1.5，yaw -= Δx×0.75。
  - PlayControl：暂停=线程等待不销毁；速度 0.01~2 实时生效；档 200/100/50Hz。
  - DialogComponents：卡片=真实 3D 预览（scale=卡宽/110）。
  - **无网格吸附**，位置自由连续。
- ⚠️ Assets/Scripts 在 sparse-checkout 外，看代码需 `git sparse-checkout add Assets/Scripts`。

## 5. 测试脚本（都在 /tmp，可能已丢，可重建）
- `probe4.mjs`：放置电池+开关+电阻+地→仿真→读数断言 + UI 控件断言。
- `probe8.mjs`：模拟真实用户点击流（选中→点pin→点pin→出线）。
- `shot.mjs`：裸截图。playwright 从 pl-town 借：
  `import pw from "/workspace/projects/pl-town/node_modules/playwright/index.js"`。
- 截图基线：/tmp/ui_sim.png（最新全景）、/tmp/unity_cam.png（Unity 取景）、
  /tmp/battery_zoom.png（电池材质问题现场）。

## 6. 提交约定
- 本仓随便 commit（sin 说过）；引擎改动才走 NetLogo-Mobile/Phy-Engine 的 PR。
- 当前提交包含：web/ 全部前端 + tools 资产管线修复 + 重提取的 GLB + 本文档。

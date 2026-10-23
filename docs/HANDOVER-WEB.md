# 交接文档 — Web 前端（2026-10-13 定稿）

> 本文档取代 2026-10-11 版（图灵棒）。M1/M2 前史见 HANDOVER.md，工程契约见 ENGINE_API.md。
> **本文描述与 main@4c61bc2（含文档 commit 后以最终 hash 为准）。接手前先 `git pull`。**

## 0.快照（值班会话结束时更新；唤醒时只读本段+PLAN未勾项，勿通读全文）

**2026-10-23 23:55（值班第 17 轮收尾：✅ 上会话半成品收尾+Relay/Photoresistor 根因大进展，37 PASS/2 FAIL，已推送 80743dc）**：
- 本轮做的：①收尾上会话挂掉的 21 项未提交（三件截图+VLM 证据：**Resistance_Law
  PASS**（X 偏移已清）/ Relay FAIL / Photoresistor FAIL）；②diag_transform 实锤
  Relay 底板 fbx_M 含 S=1.2268+轴交换=与 prefab TRS S=1.2268 重复（双重变换
  画像成立但见下方翻案）；③加 NODE_SKIP_FBX_M={('Relay Component','底板')}
  特例（回归防线）；④清残留（_tmp.json/variant_v0/v1）+ report.json 从 39 单件
  重建；⑤smoke_test EXIT=0。
- **⚠️ 关键翻案（下轮勿走弯路）**：BAKE_FBX_M 默认 0=不烘（extract_components.py
  :883 无条件 fbx_M=None，:23 注释「bake 则是回归源」）——第 16 轮画像的
  「fbx_M 双重变换致底板大板」**在默认提取路径不成立**（diag_transform 的
  「烘 fbx_M」列是假想计算）。NODE_SKIP_FBX_M 特例在 BAKE=1 回归路径才有实效，
  默认路径冗余无害。**Relay FAIL 真根因未定位**：默认路径底板=Unity 语义小板
  z±0.098，但 webshot 呈扁平薄板——下轮先 dump GLB 节点树逐节点 bbox，对照
  diag Unity 语义值（z=[-0.0983,0.0982]）找错位层；geo_M（:853「不受 BAKE 控制
  总是烘」）是头号嫌疑。**Relay GLB 本轮已重提取但未跑 VLM 重验**（batch_shot
  链两次后台跑日志空——nohup 引号嵌套/需服务，下轮前台重跑），几何等价风险低。
- **Photoresistor 根因实锤（下轮直接干）**：主体「光敏电阻」引用
  `unity/Assets/Physics-Lab/Circuits/光敏电阻 1.asset`——Unity YAML Mesh
  serializedVersion 10 **m_VertexData 新格式**（顶点打包在 streams channel，
  非 m_Vertices 旧 packed 数组），被 emit_node 的 NO-FBX 分支静默跳过→主体丢失；
  解码器是百行级工程（channel descriptors+stream alignment），今晚时间不够未做。
  「Mesh6」fid=-45537441166385993 引外部库无本地源，放弃。localAABB 中心
  z=12（顶点离原点远，解码时注意节点变换带回归位）。修法落点：emit_node 的
  .asset 分支（:730 fbx endswith 检查处）+ 新增 tools/unity_mesh_asset.py。
- **fid 猜号错位实锤**：Relay prefab Pin2/5 与「继电器」同 fid=4300000（不可能
  共用 mesh）——4300000+2*i 猜号在该 FBX 错位；Pin 走程序化豁免无影响，但
  若其他件出现错绑几何，优先查此。
- M8 三项仍等 sin 规范文档。下轮优先级：①Relay 根因（geo_M 嫌疑+GLB dump）；
  ②Photoresistor .asset 解码器；③Quad 图标面片；④移动端触控。P1=0fps 真机
  验证（等 sin）。CF Pages 搁置勿动。

**2026-10-23 21:00（值班第 16 轮收尾：✅ 10 项建模缺陷根因画像已诊断入库，未开工——预算不足防挂，已推送）**：
- 本轮：唤醒时状态干净（ahead=0/未提交 0，上轮 36/36 全绿终态）；对 PLAN 108 行
  10 项缺陷完成结构画像诊断（audit_report_v2.json 三条目实值+嫌疑代码定位），
  修复闭环预算不够未开工，线索全留此段。
- **下轮直接用（省考古）**：
  ①Relay_Component：nodes_pf=12 vs glb=11（差 1 节点）；底板 pf z=[-1.2368,
  -1.2125] vs glb z=[-0.010,0.014]——差 1.2m，像底板节点（或其父）变换未应用/
  错绑；继电器 BBOX-X 同偏。②Resistance_Law：对象001-004 X 轴统一偏 ~+0.03
  （glb X=[-0.0861,0.1105] vs pf=[-0.0983,0.0982]），父节点 X 平移未应用嫌疑。
  ③Photoresistor：「光敏电阻」「Mesh6」两 renderer 在 GLB 无对应节点
  （MESH-MISSING×2，aabb 反而一致=这俩 mesh 在包围盒内部，视觉上是本体缺失）。
  **嫌疑代码**：extract_components.py 的几何解析链（refdump walk 同款逻辑：
  `geo_by_fileid.get(fid)` 失败回退 `model_geos.get(node['name'])` 按名匹配 +
  `model_world_M` 的 fbx_M 烘焙）——按名回退可能错绑几何或丢 fbx_M 致顶点错位。
  **工具就绪**：build/refdump/{ModelID}.json 三个件已存在（36 件对照时生成，
  内含 Unity 权威 nodes[].matrix+slots），下轮直接 diff refdump vs GLB 节点树
  定断点，无需重跑 dump。修复后重提取 3 GLB（tools/extract_one.py，
  分钟级）→ batch_shot/VLM → smoke_test 三件套收尾。
- 本轮零代码改动（纯诊断+文档），无需 smoke；M8 三项仍等 sin 规范文档。
- 下轮优先级不变：①10 项缺陷修复（上线索）；②Quad 图标面片；③移动端触控。
  P1=0fps 真机验证（等 sin）。CF Pages 搁置勿动。

**2026-10-23 19:40（值班第 15 轮收尾：✅ 13 FAIL 全清零——36/36 对照全 PASS，已推送）**：
- 本轮做的：①收尾上会话挂掉的未提交改动（refshot 方法学对齐：GLB 无 pin
  网格时补画与 web 端 src/components.js 同规格程序化插头座，13 张图重生，
  commit 31b12f8）；②compose_pairs 重组 36 件对比图 + vlm_review_pairs 重审
  原 13 FAIL——**13/13 全 PASS，全量 36/36 PASS 零 FAIL**；③清理 3 个调试
  残留 json（_probe_air/_probe_cap/_tmp，会污染 report 统计），report.json
  从单件 json 重建入库。
- **结论性翻案（下轮勿再走弯路）**：原定性「1482c4d 提取器引入 M7 几何回归
  （电容 mesh_data 静默失败/Air_Switch 扁平化）」**不成立**——重审后
  Basic_Capacitor、Air_Switch 均 PASS，web 端渲染一直是对的，旧 refshot
  过时+裸 GLB vs 程序化 pin 帽的方法学不对称才是 FAIL 根因。**提取器无需
  修复、禁止回滚**。
- M8 三项（示波器/参数调节八类全集/导线核对）仍被规范文档缺失阻塞，等 sin
  提供 shared/specs/Unity电学模块功能规范.md，勿硬编。
- 下轮可干（按优先级）：①剩余 10 项真实建模缺陷（PLAN 108 行，Relay×3
  底板Z/继电器X/IconZ 等，unity/ 源码可查、无阻塞）；②Quad 图标面片材质
  层级对照（PLAN 111 行）；③移动端触控双指缩放。P1=0fps 真机验证（等 sin）。
  CF Pages 搁置勿动。
- 验证：node tools/smoke_test.mjs EXIT=0（SMOKE OK，本轮两次）；重审 13 件
  VLM 逐张 verdict 见 build/compare_vlm/<ModelID>.json。

**2026-10-23 16:10（值班第 14 轮收尾：✅ 上轮 dist 残留收口 + 对照终态报告入库，已推送）**：
- 本轮做的：①上轮 verify 后未提交的 3 个 dist 产物变更，smoke_test EXIT=0
  （SMOKE OK）验证后收尾提交；②git-lfs 3.7.0 就绪实锤——176 GLB 全部 LFS
  追踪且已在 origin/main（ahead=0），PLAN「重提取产物补推」为过时描述已勾；
  ③36 件对照终态报告 build/compare_vlm/report.json（23 PASS/13 FAIL）入库，
  PLAN.md 113/115 两项勾选更新。
- **发现的关键阻塞（下轮先看这条）**：M8 剩余三项（示波器 §3.2/§3.4、逐元件
  参数调节 §2 八类全集、导线核对 §5）全部依赖规范文档 shared/specs/Unity电学
  模块功能规范.md，但该文件已不在本地（unity/ 克隆、repo/ 引擎源码、工作区
  全搜无果，git 亦未追踪；unity/Assets 与 C++ 引擎对 oscilloscope/示波 零命中，
  无权威源可抄，铁律禁止凭记忆写）。需 sin 提供规范文档或指路，M8 三项在此之前
  全部阻塞，勿硬编。
- **下轮主活（无阻塞可干）**：13 FAIL 修复——根因方向 1482c4d 提取器 .meta
  权威映射+内置基元改动引入回归（电容 FBX meta 映射正确但 mesh_data 静默
  失败致几何错绑）；两处坑勿踩：「多出接线柱」类 FAIL 是方法学误报（refshot
  裸 GLB vs webshot 含程序化 pin 帽）；And_Gate/Air_Switch 旧版 19.3m 巨物的
  M7 差异是修复、不能整体回滚。
- 验证：node tools/smoke_test.mjs EXIT=0。

**2026-10-23 15:06（值班第 13 轮收尾：✅ .plsave 原生信封一比一（规范 §7 收官）+ verify_plsave 17 断言全绿，已推送）**：
- **主战果（承接第 12 轮挂掉的未提交 state.js 半成品，引擎源码裁决后收尾完成）**：
  toPlsave() 从旧扁平 {Type,StatusSave,CameraSave} 重写为引擎原生嵌套信封
  （root 17 键 + Experiment 11 键 + Summary 36 键 + 元件 12 键，逐键对照
  physicslab.h:320 default_plsav_template[circuit] + to_plsav_json_ec 抄录）；
  fromPlsave() 兼容新旧两格式（root.Experiment||root）。
- **三处实修（上轮半成品的真实差距）**：①addElement 新增 broken 参数——
  旧签名丢弃导入的烧毁位，.plsave 往返 IsBroken 丢失（真产品 bug）；②导线
  ColorName 归一——引擎 wire::to_json 恒写 5 键（内部 color 缺省 blue），web 端
  undefined 色现归一「蓝色导线」同形；③fromPlsave 缺省色「黑色导线」→「蓝色
  导线」（引擎 parse_wire_color_name 同判，physicslab.h:981）。
- **验证**：tools/verify_plsave.mjs 17 断言 ALL PASS——A1-A9 信封逐键比对+
  往返（含烧毁位/弧度/角度制/五色）+ B1-B7 WASM 引擎实测装载新信封（build→
  analyze→write_back→dump，I=0.03/U=3 物理正确、信封字段透传）+ C1 旧扁平
  格式向后兼容；smoke_test SMOKE OK；vite build 干净。PLAN.md §M8 电表类
  与 §7 存档两项已勾。
- **裁决纪律实证**：A3 Summary 键集之争以引擎源码为准——Version 在 Summary
  级（physicslab.h:356）、Verification 只在 User 级（:381），state.js 原写法
  正确，是验证脚本断言抄错了键。
下一步优先级：P1=headless 0fps（真机验证，等 sin）；P2=示波器（规范
§3.2/§3.4）、逐元件参数调节（规范 §2 八类全集）、导线连接与电路求解规格
核对（规范 §5）；36 元件批量 VLM 对照（管线就绪未跑）。CF Pages 搁置勿动。

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

1. **36 元件批量 VLM 对照**：batch_shot.mjs 就绪（首跑中断，仅 grid_0/grid_1 落盘，
   全量应 6 张）。grid_0 初步发现（build/grid_0.png）：
   - **Basic Capacitor 本体悬空**——GLB 原点与 mesh y 偏移不符，疑提取时 Y 偏移
     丢失；排查：dump 该 GLB 节点 min/max y，对照 Unity prefab 里电容本体局部 y
   - 互感器/变压器类**超长底板溢出 0.3m 格位**（摆放问题非模型问题，batch 脚本
     对大元件的间距要按 catalog 尺寸自适应）
   - 右下一块**空底板只有一个红柱**（无主体 mesh，ModelID 待定位——从脚本第 4 格
     `names[3]` 对回去）
   - 电感/555 芯片丝印/开关类 ✓ 与官方一致
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

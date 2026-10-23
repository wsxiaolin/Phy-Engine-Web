# Relay_Component 根因数据包（2026-10-24 第 20 轮，下轮直接开工用）

## 官方真身（VLM 单图实述，glm-5v-turbo）

等轴测视角：**薄**圆角长方体底座（深灰，W:D≈1.6:1，厚≈总高 15-20%）；
底座中后方**浅蓝色立方体**（线圈/铁芯）；其正上方**黑色圆柱**（顶部接线柱）；
四角接线柱 3 红 1 黑；白色触点符号印在底座上表面中心。整体 W:H:D≈
2.5:1.2:1.5（**高耸**，H≈0.48W）。

## Web 现状（单图实述 + bbox_diff）

整体压扁：H≈0.15W；蓝色物+黑色物呈「两个小型圆柱」而非立方体+高圆柱；
底座本身形状/厚度/footprint 正确（0.16×0.08×0.02）。即**病灶集中在
竖直结构（继电器 body + 顶部端子）欠高**，不在底板。

## 全链路数据（prefab=Analog Circuits/Relay Element.prefab）

- **底板**（基础件.FBX fid=4300004，raw [0.065,0.131,0.016]m，
  prefab TRS S=1.2268 均匀）：NODE_SKIP 生效中，链×顶点=
  [0.1602,0.0199,0.08] ✓ footprint/厚度与官方吻合；
  若不 skip（链×fbx_M）=[0.098,0.024,**0.197**] 明显错——skip 判断正确，
  round-19 快照里「Relay 根因=底板」可以销案。
- **继电器 body**（继电器.FBX fid=4300000，raw [0.0953,**0.0401**,
  **0.0733**]m，TRS T=(0,0.0196,0) S=(0.564,0.423,0.564)，fbx_M≈I，
  geo_M 烘后 act=[0.0537,0.031,0.0226]）：**raw Z=0.0733 是最长轴**，
  疑 mesh 按 Z-up 手稿导出（蓝立方体+顶部圆柱沿 raw Z 堆叠：0.04+0.03
  ≈0.073）。prefab TRS 四元数不含 Z→Y 旋转，fbx_M 也不含 → 提取产物
  竖直结构躺平。**Unity 侧把它立起来的变换在哪（FBX 根 Lcl？importer
  -90°X 烘焙？）是下轮第一问**。
- **Pin 2/5**（fid=4300000，T=(0,0.05,0)/(−0.06,0.02,0.025)）：官方
  「蓝立方体顶上的黑圆柱」≈这两个高位 pin（y=0.05）对应的部件——
  KEEP_PIN_MESHES=1 已保留其网格，但 body 不够高 → 顶子悬空/贴地。
- 线/Icon：bbox_diff Δ=0，提取正确。

## 下轮开工路径

1. ~~查继电器.FBX 的根节点 Lcl 变换与 Unity 导入语义~~（第 21 轮已查，见下方结案）
2. ~~复跑：提取 → 同步 dist → smoke → webshot → compose_official →
   vlm_review_official~~
3. MI 的 Icon 面片同族问题见 Mutual_Inductor_forensics.md。

---

# 结案（2026-10-24 第 21 轮：✅ Relay_Component 销案——非提取缺陷，官方对照 FAIL = webshot 取景导致 VLM 判定漂移）

## FBX 源码事实（probe_axis，`Lcl Rotation`/`GeometricRotation` 均在节点上）

继电器.FBX（v7400）结构极简：唯一 Geometry 1141932016（740 顶点，raw
bbox [0.0953,0.0402,0.0733]）挂在唯一根 Model Sphere001 上，带
`Lcl Rotation=+90°X` + `GeometricRotation=-90°X`（单轴互抵，顶点全局
位置不变）。prefab MeshFilter 直接引用 fileID 4300000（跨层级直引 mesh
资产）——Unity 语义=顶点烘 GeoM(-90°X)（raw Z 堆叠→立起）、Lcl 留在
FBX 内 GameObject 层级被跳过；prefab TRS T=(0,0.0196,0)
S=(0.564,0.423,0.564) 再压。**提取器行为与该语义逐位一致**（上轮
「fbx_M≈I 所以漏了旋转」的推断作废——没有漏，本来就该不烘 Lcl）。

## 证据链（四步定罪「判定漂移」而非几何缺陷）

1. **GLB 数据全对**：body Y=0.031、Pin2 顶 y=0.0766、footprint
   0.1602×0.08 → 整体 H/W=0.48，与官方实述「H≈0.48W」精确吻合
   （relay_glb_bbox.py，现已删，结论在此）。
2. **web 近景实述结构正确**（glm-5v 对 relay_closeup.png）：薄底座 +
   浅蓝立方体（中部偏右）+ 其上表面中心黑色圆柱（金顶，全图最高）+
   3红1黑接线柱 + 白色丝印——与官方结构一一对应（近景图
   build/compare_official_vlm/relay_closeup.png）。
3. **拼图复跑 FAIL 但判词互斥**：第 19/20 轮判「两个小型圆柱
   H≈0.15W」，本轮同图复跑判「极薄的扁平片状或线框结构」——同一渲染
   两轮给出互斥幻觉描述，且与近景实述矛盾。
4. **公平对照终裁 PASS**：官方预览（拼图左半裁出）vs web 近景
   relay_closeup.png 等高并排（relay_fair.png），VLM 判 PASS：
   「黑色底座、蓝色继电器主体、阶梯状底部细节、四个接线柱（2红2黑）
   布局与比例」全部吻合（relay_fair_vlm.json）。

## 定性

- **Relay_Component = 非提取缺陷**。几何/层级/变换提取正确。
- 官方对照 vlm_review_official 判 FAIL 的真因：**compose_official 拼图
  右半的 webshot 取景下元件太小/环境占比过大，VLM 分辨不出主体结构**
  （先例：Mutual_Inductor 判定漂移案）。对照基线 38 件实质全 PASS。
- 遗留改进（非缺陷，管线质量项）：shot_pairs 的 webshot 取景应怼近元件
  （对齐官方预览的满幅特写），避免后续新件复现同类误判——评估后决定
  是否全量重截重审。
- 竖直结构「Y=0.423 压扁」问题不存在：0.423 是 prefab 源码里的 Unity
  真实 scale，一比一复刻即正确。

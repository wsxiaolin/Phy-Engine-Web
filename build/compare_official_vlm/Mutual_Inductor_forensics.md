# Mutual_Inductor「回归疑云」取证结案（2026-10-24 第 20 轮）

## 结论

**第 18/19 轮怀疑的「重提取引入回归」不成立**。真实情况：
几何自 2349208 起字节级未变，新旧 webshot 像素级一致；round-17 的 PASS 与
round-19 的 FAIL 是**同一张图上的 VLM 判定漂移**。复审两次 FAIL 指向的
**唯一真实差距**是图标面片（线圈符号）画在了底座表面，而官方预览里白色
标记只印在中心 IC 表面——属已知缺陷类（PLAN #111「Unity 内置 Quad 图标
面片」），非本轮回归。

## 证据链（可复跑）

1. **GLB 未变**：`build/assets/components/Mutual_Inductor.glb` 与
   `web/dist/assets/components/Mutual_Inductor.glb` sha256 相同
   （`d686311f…`），git 历史显示最后一次变更是 2349208（round-17），
   第 18 轮 87 件重提取未改变其字节。
2. **catalog 条目未变**：2349208 与 HEAD 的 catalog.json MI 条目 diff 为空。
3. **webshot 像素一致**：`git lfs fetch origin 2349208` 取旧图后 PIL diff：
   720×720，diff bbox 仅 (597,19)-(620,32)（右上角 HUD 区），L>12 像素
   占 0.02%。即 round-17 PASS 与 round-19 FAIL 看的是同一画面。
4. **单图实述（glm-5v-turbo，本轮）**：
   - 官方图：平放模块，圆角矩形**厚**基座（侧面可见黑色立边），中心平放
     IC 芯片，白色线条只在 IC 上表面，W:H:D≈3.5:1:2。
   - webshot：平放，**厚块感明显**（非薄片），圆角，中心灰色 IC 平贴
     底座正中；唯一差距=白色线圈符号画在底座表面、环绕 IC（覆盖较大），
     官方则只在 IC 表面。
   - 「基座极薄 PCB」的 FAIL 表述与实述矛盾，判定为幻觉成分；但
     「白色图案位置差异 + IC 细节」在两轮复审中稳定复现，为真差距。
5. **复审再跑**：`vlm_review_official.py Mutual_Inductor` → FAIL
   （issues：底座表面多出白色走线/线圈图案、中央芯片细节差异）——与
   round-19 同向，排「一次性抽风」。

## refdump 对 MI 不可信（旁证）

`build/refdump/Mutual Inductor.json` 的期望值自相矛盾：Icon 竖直 0.138×0.247
面片、底板 dims [0.059, **0.78**, 0.41]（0.78m 高的「底板」），与官方预览
（平放、厚≈1/3.5 宽）完全不符。refdump 的组成路径对 MI/Relay 这类
「prefab 链 + 多 FBX（互感器.FBX 英寸单位 / 基础件.FBX）+ builtin Quad」
结构未被审计覆盖，其 exp 不能作为这两件的权威。

## 下轮动作（优先级）

1. 图标面片矫正：MI 的 Icon/4×Quad 应贴在 IC（互感器 body）上表面且缩至
   IC 尺寸（官方标记 ~0.05m 级，当前 0.124m 铺满底座）。疑点：builtin
   Quad 的 TRS 链与 `互感器` group 的循环旋转+非均匀缩放（S≈0.414/0.251/
   0.239）组合，与 Relay 的「Icon Z」同族——可一并修。
2. 见 `Relay_Component_forensics.md`（同轮产出）。

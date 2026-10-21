#!/usr/bin/env bash
# 值班唤醒快照 —— 每次会话第一步【只跑这一个脚本】，一次拿到全部起步状态。
# 用法: bash tools/wakeup.sh   （输出 ~60 行，勿再逐文件通读 docs/*.md）
# 会话结束时: commit+push 后同步更新 HANDOVER-WEB.md 的「快照」段。
cd "$(dirname "$0")/.." || exit 1

echo "######## git ########"
git fetch origin -q 2>/dev/null
UP=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null)
echo "branch: $(git branch --show-current) -> ${UP:-无上游}"
AHEAD=$(git rev-list --count @{u}..HEAD 2>/dev/null); BEHIND=$(git rev-list --count HEAD..@{u} 2>/dev/null)
echo "ahead=$AHEAD behind=$BEHIND  (未推送 commit / 远端有新提交)"
echo "--- 最近 5 条 commit ---"
git log --oneline -5
DIRTY=$(git status -s | wc -l)
echo "--- 未提交改动: $DIRTY 个（>0 说明上会话干一半挂了，先验证收尾再干活）---"
[ "$DIRTY" -gt 0 ] && git status -s | head -8

echo
echo "######## 快照段（HANDOVER-WEB.md §0 快照，即上次会话终态）########"
awk '/^## 0\.快照/{f=1;next} /^## /{if(f)exit} f' docs/HANDOVER-WEB.md | head -40

echo
echo "######## 遗留未完成项（PLAN.md 未勾选，前 12 条）########"
grep -n '^\s*- \[ \]' docs/PLAN.md | grep -v '~~' | head -12

echo
echo "######## 提示 ########"
echo "· 长任务（批量截图/VLM 跑批）用子壳后台+轮询: ( cmd >log 2>&1 & ) 防挂死"
echo "· 视觉改动必须截图实测+VLM，Unity 源码参数为准（unity/ 克隆）"
echo "· push 前本地验证（smoke_test.mjs EXIT=0 是底线）"

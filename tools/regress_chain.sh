#!/bin/bash
# 2026-10-22 全量镜像修复回归链：截图(断点续跑) → compose_official → vlm_review_official
cd /home/z/my-project/phy-engine-web/web || exit 1
FORCE= node shot_pairs.mjs >> /tmp/regress_shot.log 2>&1
echo "SHOT_EXIT=$?" >> /tmp/regress_shot.log
if ! tail -1 /tmp/regress_shot.log | grep -q 'SHOT_EXIT=0'; then exit 1; fi
cd /home/z/my-project/phy-engine-web
python3 tools/compose_official.py > /tmp/regress_compose.log 2>&1
echo "COMPOSE_EXIT=$?" >> /tmp/regress_compose.log
if ! tail -1 /tmp/regress_compose.log | grep -q 'COMPOSE_EXIT=0'; then exit 1; fi
python3 tools/vlm_review_official.py > /tmp/regress_vlm.log 2>&1
echo "VLM_EXIT=$?" >> /tmp/regress_vlm.log

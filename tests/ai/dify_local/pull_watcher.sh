#!/bin/bash
# 守望者：每10分钟交替源重试，两个大镜像齐了自动退出
DOCKER="/c/Program Files/Docker/Docker/resources/bin/docker.exe"
MIRRORS=("docker.m.daocloud.io" "docker.1ms.run")
> /e/AI/fab-ai-services/watcher_status.txt
for round in $(seq 1 12); do
  have_web=$("$DOCKER" images -q dify-web:0.10.3 | wc -l)
  have_api=$("$DOCKER" images -q dify-api:0.10.3 | wc -l)
  if [ "$have_web" -ge 1 ] && [ "$have_api" -ge 1 ]; then
    echo "[$(date +%H:%M:%S)] BOTH READY" >> /e/AI/fab-ai-services/watcher_status.txt
    break
  fi
  m=${MIRRORS[$((round % 2))]}
  if [ "$have_web" -eq 0 ]; then
    echo "[$(date +%H:%M:%S)] round$round: dify-web via $m" >> /e/AI/fab-ai-services/watcher_status.txt
    if "$DOCKER" pull "$m/langgenius/dify-web:0.10.3" >> /e/AI/fab-ai-services/watcher_pull.log 2>&1; then
      "$DOCKER" tag "$m/langgenius/dify-web:0.10.3" dify-web:0.10.3
      echo "[$(date +%H:%M:%S)] dify-web DONE" >> /e/AI/fab-ai-services/watcher_status.txt
      continue
    fi
  fi
  have_web=$("$DOCKER" images -q dify-web:0.10.3 | wc -l)
  if [ "$have_web" -ge 1 ] && [ "$("$DOCKER" images -q dify-api:0.10.3 | wc -l)" -eq 0 ]; then
    echo "[$(date +%H:%M:%S)] round$round: dify-api via $m" >> /e/AI/fab-ai-services/watcher_status.txt
    if "$DOCKER" pull "$m/langgenius/dify-api:0.10.3" >> /e/AI/fab-ai-services/watcher_pull.log 2>&1; then
      "$DOCKER" tag "$m/langgenius/dify-api:0.10.3" dify-api:0.10.3
      echo "[$(date +%H:%M:%S)] dify-api DONE" >> /e/AI/fab-ai-services/watcher_status.txt
      continue
    fi
  fi
  sleep 600
done

#!/bin/bash
DOCKER="/c/Program Files/Docker/Docker/resources/bin/docker.exe"
MIRRORS=("docker.m.daocloud.io" "hub.rat.dev" "docker.1ms.run")
IMAGES=("semitechnologies/weaviate:1.25.4" "langgenius/dify-sandbox:0.2.1" "langgenius/dify-web:0.10.3" "langgenius/dify-api:0.10.3")
> /e/AI/fab-ai-services/final_status.txt
for img in "${IMAGES[@]}"; do
  ok=0
  for m in "${MIRRORS[@]}"; do
    echo "[$(date +%H:%M:%S)] pull $m/$img" >> /e/AI/fab-ai-services/final_status.txt
    if timeout 420 "$DOCKER" pull "$m/$img" >> "/e/AI/fab-ai-services/final_${img//[:\/]/__}.log" 2>&1; then
      "$DOCKER" tag "$m/$img" "$img"
      echo "[$(date +%H:%M:%S)] DONE $img (via $m)" >> /e/AI/fab-ai-services/final_status.txt
      ok=1; break
    fi
    sleep 10
  done
  [ $ok -eq 0 ] && echo "[$(date +%H:%M:%S)] FAILED $img (全部源)" >> /e/AI/fab-ai-services/final_status.txt
done
echo "[$(date +%H:%M:%S)] ALL DONE" >> /e/AI/fab-ai-services/final_status.txt

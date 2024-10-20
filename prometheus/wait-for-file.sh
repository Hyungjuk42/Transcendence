#!/bin/bash

# Check if the correct number of arguments was provided
if [ "$#" -lt 1 ]; then
  echo "Usage: $0 file1 [file2 ...] [timeout]"
  exit 1
fi

# 배열로 파일 목록 받기
FILES=("${@:1:$#-1}")
TIMEOUT=${@: -1} # 마지막 인자를 timeout으로 설정, 없으면 기본값으로 0

WAIT_INTERVAL=1
TIME_WAITED=0

# 파일들이 모두 존재할 때까지 대기
while true; do
  all_files_exist=true

  # 파일들을 확인하며 존재 여부 검사
  for file in "${FILES[@]}"; do
    if [ ! -f "$file" ]; then
      all_files_exist=false
      break
    fi
  done

  # 모든 파일이 존재하면 종료
  if $all_files_exist; then
    echo "All required files found"
    exit 0
  fi

  # timeout 체크
  if [ "$TIMEOUT" -gt 0 ] && [ "$TIME_WAITED" -ge "$TIMEOUT" ]; then
    echo "Timeout reached: Not all files found"
    exit 1
  fi

  # 대기
  sleep $WAIT_INTERVAL
  TIME_WAITED=$((TIME_WAITED + WAIT_INTERVAL))
done

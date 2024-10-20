#!/bin/bash

# 변수로 경로와 실행할 명령을 입력받음
FILE=$1
TIMEOUT=${2:-60}
shift 2
CMD="$@"

# wait-for-file 스크립트를 사용하여 인증서 파일이 존재할 때까지 대기
/usr/local/bin/wait-for-file.sh "$FILE" "$TIMEOUT"

# 인증서 파일이 존재하면 입력받은 명령 실행
exec $CMD

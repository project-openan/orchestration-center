#!/bin/bash

# 通过进程名停止服务
# 使用方法: ./stop.sh

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 进程名
PROCESS_NAME="orchestrate.start"

echo "正在停止服务..."

# 查找进程
PIDS=$(pgrep -f "$PROCESS_NAME" 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo -e "${YELLOW}未找到运行中的服务${NC}"
    exit 0
fi

echo "找到进程 PID: $PIDS"

# 停止进程
for PID in $PIDS; do
    kill $PID 2>/dev/null
done

sleep 2

# 检查并强制停止残留进程
PIDS=$(pgrep -f "$PROCESS_NAME" 2>/dev/null)
if [ -n "$PIDS" ]; then
    echo -e "${YELLOW}进程未响应，强制停止...${NC}"
    for PID in $PIDS; do
        kill -9 $PID 2>/dev/null
    done
    sleep 1
fi

# 检查是否停止
if ps -p $PID > /dev/null 2>&1; then
    echo -e "${YELLOW}进程未响应，强制停止...${NC}"
    kill -9 $PID 2>/dev/null
    sleep 1
fi

echo -e "${GREEN}服务已停止${NC}"
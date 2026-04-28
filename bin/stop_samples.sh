#!/bin/bash


RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Get the absolute path of the script's directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# PID 文件路径（与启动脚本保持一致）
BACKEND_PID_FILE="${SCRIPT_DIR}/tmp/backend.pid"
FRONTEND_PID_FILE="${SCRIPT_DIR}/tmp/frontend.pid"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Stopping Services${NC}"
echo -e "${BLUE}========================================${NC}"

# 停止后端服务
echo -e "${YELLOW}Stopping backend service...${NC}"

# 方法1：通过 PID 文件停止
if [ -f "$BACKEND_PID_FILE" ]; then
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")
    if kill -0 $BACKEND_PID 2>/dev/null; then
        kill $BACKEND_PID 2>/dev/null
        echo -e "${GREEN}Backend stopped (PID: $BACKEND_PID)${NC}"
    else
        echo -e "${YELLOW}Backend PID file exists but process not running${NC}"
    fi
    rm -f "$BACKEND_PID_FILE"
else
    # 方法2：通过进程名停止
    echo -e "${YELLOW}Looking for backend process by name...${NC}"
    BACKEND_PIDS=$(pgrep -f "python -m samples.start_agents_server" 2>/dev/null)

    if [ -z "$BACKEND_PIDS" ]; then
        BACKEND_PIDS=$(pgrep -f "samples.start_agents_server" 2>/dev/null)
    fi

    if [ -n "$BACKEND_PIDS" ]; then
        for PID in $BACKEND_PIDS; do
            kill $PID 2>/dev/null
            echo -e "${GREEN}Backend stopped (PID: $PID)${NC}"
        done
    else
        echo -e "${YELLOW}No running backend process found${NC}"
    fi
fi

sleep 2

# 强制停止残留的后端进程
BACKEND_PIDS=$(pgrep -f "python -m samples.start_agents_server" 2>/dev/null)
if [ -n "$BACKEND_PIDS" ]; then
    echo -e "${YELLOW}Force stopping remaining backend processes...${NC}"
    for PID in $BACKEND_PIDS; do
        kill -9 $PID 2>/dev/null
        echo -e "${GREEN}Backend force stopped (PID: $PID)${NC}"
    done
fi

# 停止前端服务
echo ""
echo -e "${YELLOW}Stopping frontend service...${NC}"

# 方法1：通过 PID 文件停止
if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        kill $FRONTEND_PID 2>/dev/null
        echo -e "${GREEN}Frontend stopped (PID: $FRONTEND_PID)${NC}"
    else
        echo -e "${YELLOW}Frontend PID file exists but process not running${NC}"
    fi
    rm -f "$FRONTEND_PID_FILE"
else
    # 方法2：通过端口查找（如果前端使用固定端口，如 3000）
    FRONTEND_PORT=3003
    if command -v lsof &> /dev/null; then
        FRONTEND_PID=$(lsof -ti:$FRONTEND_PORT 2>/dev/null)
        if [ -n "$FRONTEND_PID" ]; then
            kill $FRONTEND_PID 2>/dev/null
            echo -e "${GREEN}Frontend stopped (PID: $FRONTEND_PID, Port: $FRONTEND_PORT)${NC}"
        fi
    fi

    # 方法3：通过进程名停止
    if [ -z "$FRONTEND_PID" ]; then
        FRONTEND_PIDS=$(pgrep -f "npm start" 2>/dev/null)
        if [ -z "$FRONTEND_PIDS" ]; then
            FRONTEND_PIDS=$(pgrep -f "npm run dev" 2>/dev/null)
        fi
        if [ -z "$FRONTEND_PIDS" ]; then
            FRONTEND_PIDS=$(pgrep -f "node.*workflow-designer" 2>/dev/null)
        fi

        if [ -n "$FRONTEND_PIDS" ]; then
            for PID in $FRONTEND_PIDS; do
                kill $PID 2>/dev/null
                echo -e "${GREEN}Frontend stopped (PID: $PID)${NC}"
            done
        else
            echo -e "${YELLOW}No running frontend process found${NC}"
        fi
    fi
fi

sleep 2

# 强制停止残留的前端进程
FRONTEND_PIDS=$(pgrep -f "npm" | xargs pgrep -f "workflow-designer" 2>/dev/null)
if [ -n "$FRONTEND_PIDS" ]; then
    echo -e "${YELLOW}Force stopping remaining frontend processes...${NC}"
    for PID in $FRONTEND_PIDS; do
        kill -9 $PID 2>/dev/null
        echo -e "${GREEN}Frontend force stopped (PID: $PID)${NC}"
    done
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}All services stopped${NC}"
echo -e "${GREEN}========================================${NC}"
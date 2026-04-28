#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Get the absolute path of the script's directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ROOT_DIR="${SCRIPT_DIR}/.."
TARGET_DIR="${SCRIPT_DIR}/../samples"
FRONTEND_DIR="${SCRIPT_DIR}/../workflow-designer"

if [ -d "$ROOT_DIR" ]; then
    ROOT_DIR="$(cd "$ROOT_DIR" && pwd)"
    cd "$ROOT_DIR" || exit 1
    echo "Current working directory: $(pwd)"
else
    echo -e "${RED}The project root path does not exist.${NC}"
    exit 1
fi

# Check if target directory exists
if [ -d "$TARGET_DIR" ]; then
    echo -e "${GREEN}Target directory exists: $TARGET_DIR${NC}"
else
    echo -e "${RED}Error: Target directory does not exist: $TARGET_DIR${NC}"
    exit 1
fi

# Check if Python script 'preflow_orchestrator_demo.py' exists in the target directory
PYTHON_SCRIPT="${TARGET_DIR}/preflow_orchestrator_demo.py"
if [ -f "$PYTHON_SCRIPT" ]; then
    echo -e "${GREEN}Python script found: $PYTHON_SCRIPT${NC}"
else
    echo -e "${RED}Error: Python script preflow_orchestrator_demo.py does not exist in $TARGET_DIR${NC}"
    exit 1
fi

BACKEND_PID_FILE="${SCRIPT_DIR}/tmp/backend.pid"
FRONTEND_PID_FILE="${SCRIPT_DIR}/tmp/frontend.pid"

# Clean up old PID files
rm -f "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"

# ========== Frontend Startup ==========
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Starting Frontend Application${NC}"
echo -e "${BLUE}========================================${NC}"

# Check if frontend directory exists
if [ -d "$FRONTEND_DIR" ]; then
    echo -e "${GREEN}Frontend directory exists: $FRONTEND_DIR${NC}"
    cd "$FRONTEND_DIR" || {
        echo -e "${RED}Error: Cannot change to frontend directory${NC}"
        exit 1
    }

    # Check if node_modules exists, if not run npm install
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}node_modules not found, running npm install...${NC}"
        npm install --force
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: npm install failed${NC}"
            exit 1
        fi
        echo -e "${GREEN}npm install completed successfully${NC}"
    else
        echo -e "${GREEN}node_modules already exists, skipping npm install${NC}"
    fi

    # Check if package.json has a start script
    if grep -q '"start"' package.json; then
        echo -e "${GREEN}Starting frontend with 'npm start'...${NC}"
        npm start &
        FRONTEND_PID=$!
        echo $FRONTEND_PID > "$FRONTEND_PID_FILE"
        echo -e "${GREEN}Frontend started with PID: $FRONTEND_PID${NC}"
    elif grep -q '"dev"' package.json; then
        echo -e "${GREEN}Starting frontend with 'npm run dev'...${NC}"
        npm run dev &
        FRONTEND_PID=$!
        echo $FRONTEND_PID > "$FRONTEND_PID_FILE"
        echo -e "${GREEN}Frontend started with PID: $FRONTEND_PID${NC}"
    else
        echo -e "${YELLOW}No start script found in package.json${NC}"
        echo -e "${YELLOW}Please check the frontend configuration${NC}"
    fi
else
    echo -e "${RED}Error: Frontend directory does not exist: $FRONTEND_DIR${NC}"
    echo -e "${YELLOW}Continuing with backend only...${NC}"
fi

# Return to root directory
cd "$ROOT_DIR" || exit 1

# ========== Backend Startup ==========
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Starting Backend Application${NC}"
echo -e "${BLUE}========================================${NC}"

# Start the Python script
echo "Starting Python script: $PYTHON_SCRIPT"
cd "$TARGET_DIR" || exit 1
python -m samples.start_agents_server &
BACKEND_PID=$!
echo $BACKEND_PID > "$BACKEND_PID_FILE"
echo -e "${GREEN}Backend started with PID: $BACKEND_PID${NC}"

# Wait for processes
wait $BACKEND_PID

EXIT_CODE=$?
echo "Python script exit code: $EXIT_CODE"

# If backend exits, optionally kill frontend
if [ $EXIT_CODE -ne 0 ]; then
    echo -e "${YELLOW}Backend exited with error, stopping frontend...${NC}"
    if [ -n "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null
    fi
fi

exit $EXIT_CODE
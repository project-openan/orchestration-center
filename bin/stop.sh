#!/bin/bash

# Stop service by process name
# Usage: ./stop.sh

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Process name
PROCESS_NAME="orchestrate.start"

echo "Stopping service..."

# Find processes
PIDS=$(pgrep -f "$PROCESS_NAME" 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo -e "${YELLOW}No running service found${NC}"
    exit 0
fi

echo "Found process PID: $PIDS"

# Stop processes
for PID in $PIDS; do
    kill $PID 2>/dev/null
done

sleep 2

# Check and force stop remaining processes
PIDS=$(pgrep -f "$PROCESS_NAME" 2>/dev/null)
if [ -n "$PIDS" ]; then
    echo -e "${YELLOW}Process not responding, force stopping...${NC}"
    for PID in $PIDS; do
        kill -9 $PID 2>/dev/null
    done
    sleep 1
fi

# Check if stopped
if ps -p $PID > /dev/null 2>&1; then
    echo -e "${YELLOW}Process not responding, force stopping...${NC}"
    kill -9 $PID 2>/dev/null
    sleep 1
fi

echo -e "${GREEN}Service stopped${NC}"
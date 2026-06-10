#!/bin/bash

# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

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
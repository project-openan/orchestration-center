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

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get the absolute path of the script's directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ROOT_DIR="${SCRIPT_DIR}/.."
TARGET_DIR="${SCRIPT_DIR}/../orchestrate"

if [ -d "$ROOT_DIR" ]; then
    ROOT_DIR="$(cd "$ROOT_DIR" && pwd)"
    cd $ROOT_DIR
    echo "Current working directory: $(pwd)"
else
  echo "The project root path does not exist."
  exit 1
fi

# Prefer to use the packaged virtual environment Python; fallback to system python if not present
VENV_PYTHON="$ROOT_DIR/venv/bin/python"
if [ -f "$VENV_PYTHON" ]; then
    PYTHON_CMD="$VENV_PYTHON"
    echo -e "${GREEN}✓ Using built-in virtual environment Python: $PYTHON_CMD${NC}"
else
    PYTHON_CMD="python"
    echo -e "${YELLOW}⚠ Built-in virtual environment not found, using system Python: $(which $PYTHON_CMD)${NC}"
    # Optional: check if system Python version meets requirements (>=3.10)
    if ! $PYTHON_CMD -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
        echo -e "${RED}Error: System Python version is below 3.10. Please upgrade or use a full deployment package that includes a virtual environment.${NC}"
        exit 1
    fi
fi
# =====================================

# get user information
CURRENT_USER=$(whoami)
CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "⚠️  ===== Security Warning ====="
    echo "You are currently running as root!"
    echo "Executing commands as root may pose security risks. Please proceed with caution."
    echo "   It is recommended to use root privileges only when necessary."
    echo "============================="

    read -p "$(echo -e "${YELLOW}Do you want to continue?(y/n): ${NC}")" choice
    case "$choice" in
        [Yy]|[Yy][Ee][Ss])
            echo "Continue to execute..."
            ;;
        *)
            echo "Operation canceled"
            exit 0
            ;;
    esac
fi

# Passing through environment variables to Python
export APP_USER="$CURRENT_USER"
export APP_UID="$CURRENT_UID"
export APP_GID="$CURRENT_GID"
export OPENSSL_CONF="${ROOT_DIR}/etc/conf/custom_openssl.cnf"

# Check if target directory exists
if [ -d "$TARGET_DIR" ]; then
    echo "Target directory exists:$TARGET_DIR"
else
    echo "Error: Target directory does not exist: $TARGET_DIR"
    exit 1
fi

# Check if Python script 'start.py' exists in the target directory
PYTHON_SCRIPT="${TARGET_DIR}/start.py"
if [ -f "$PYTHON_SCRIPT" ]; then
    echo "Python script found:$PYTHON_SCRIPT"
else
    echo "Error: Python script start.py does not exist in $TARGET_DIR"
    exit 1
fi

# Start the Python script
echo "Starting Python script: $PYTHON_SCRIPT"

nohup "$PYTHON_CMD" -m orchestrate.start > /dev/null 2>&1 &

EXIT_CODE=$?
echo "Starting orchestrate successfully, the exit code is: $EXIT_CODE"
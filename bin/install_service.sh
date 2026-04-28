#!/bin/bash

# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE="${ROOT_DIR}/etc/systemd/deploy.conf"
SERVICE_NAME="orchestration-center"
SERVICE_FILE="${ROOT_DIR}/etc/systemd/${SERVICE_NAME}.service"
INSTALL_DIR="/opt/${SERVICE_NAME}"
PYTHON_PATH=""
INSTALL_DEPS="true"
SYSTEMD_DIR="/etc/systemd/system"

load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        while IFS='=' read -r key value || [ -n "$key" ]; do
            key=$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
            value=$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
            case "$key" in
                INSTALL_DIR) INSTALL_DIR="$value" ;;
                PYTHON_PATH) PYTHON_PATH="$value" ;;
                SERVICE_NAME) SERVICE_NAME="$value" ;;
                INSTALL_DEPS) INSTALL_DEPS="$value" ;;
            esac
        done < "$CONFIG_FILE"
    fi
}

usage() {
    echo "Usage: $0 [install|uninstall|status|start|stop|restart|enable|disable] [options]"
    echo ""
    echo "Commands:"
    echo "  install    Install the systemd service"
    echo "  uninstall  Remove the systemd service"
    echo "  status     Check service status"
    echo "  start      Start the service"
    echo "  stop       Stop the service"
    echo "  restart    Restart the service"
    echo "  enable     Enable auto-start on boot"
    echo "  disable    Disable auto-start on boot"
    echo ""
    echo "Options:"
    echo "  --dir=PATH      Override install directory"
    echo "  --python=PATH   Override Python path"
    echo "  --no-deps       Skip dependency installation"
    echo ""
    echo "Config file: etc/systemd/deploy.conf"
    exit 1
}

parse_args() {
    while [ $# -gt 1 ]; do
        case "$2" in
            --dir=*) INSTALL_DIR="${2#*=}" ;;
            --python=*) PYTHON_PATH="${2#*=}" ;;
            --no-deps) INSTALL_DEPS="false" ;;
            *) usage ;;
        esac
        shift
    done
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}Error: This command must be run as root${NC}"
        exit 1
    fi
}

install_service() {
    check_root
    load_config
    parse_args "$@"

    echo -e "${GREEN}Deploy Configuration:${NC}"
    echo "  Install Dir: $INSTALL_DIR"
    echo "  Python Path: ${PYTHON_PATH:-auto detect}"
    echo "  Install Deps: $INSTALL_DEPS"
    echo ""

    if [ ! -f "$SERVICE_FILE" ]; then
        echo -e "${RED}Error: Service file not found: $SERVICE_FILE${NC}"
        exit 1
    fi

    CURRENT_USER=${SUDO_USER:-$(whoami)}
    CURRENT_UID=$(id -u "$CURRENT_USER")
    CURRENT_GID=$(id -g "$CURRENT_USER")

    if [ -z "$PYTHON_PATH" ]; then
        PYTHON_PATH=$(which python3 2>/dev/null || which python 2>/dev/null)
    fi

    if [ -z "$PYTHON_PATH" ]; then
        echo -e "${RED}Error: Python not found. Please specify --python=PATH or set PYTHON_PATH in config${NC}"
        exit 1
    fi

    echo "Using Python: $PYTHON_PATH"
    $PYTHON_PATH --version

    if [ "$INSTALL_DIR" != "$ROOT_DIR" ]; then
        echo "Copying files to $INSTALL_DIR..."
        mkdir -p "$INSTALL_DIR"
        cp -r "$ROOT_DIR"/* "$INSTALL_DIR/"
    fi

    if [ "$INSTALL_DEPS" = "true" ]; then
        REQUIREMENTS_FILE="${INSTALL_DIR}/requirements.txt"
        if [ -f "$REQUIREMENTS_FILE" ]; then
            echo "Installing dependencies..."
            $PYTHON_PATH -m pip install -r "$REQUIREMENTS_FILE"
            if [ $? -ne 0 ]; then
                echo -e "${YELLOW}Warning: Failed to install some dependencies${NC}"
            else
                echo -e "${GREEN}Dependencies installed successfully${NC}"
            fi
        else
            echo -e "${YELLOW}Warning: requirements.txt not found${NC}"
        fi
    fi

    TEMP_SERVICE=$(mktemp)
    sed -e "s|^User=.*|User=${CURRENT_USER}|g" \
        -e "s|^Group=.*|Group=$(id -gn "$CURRENT_USER")|g" \
        -e "s|^WorkingDirectory=.*|WorkingDirectory=${INSTALL_DIR}|g" \
        -e "s|^Environment=\"APP_USER=.*|Environment=\"APP_USER=${CURRENT_USER}\"|g" \
        -e "s|^Environment=\"APP_UID=.*|Environment=\"APP_UID=${CURRENT_UID}\"|g" \
        -e "s|^Environment=\"APP_GID=.*|Environment=\"APP_GID=${CURRENT_GID}\"|g" \
        -e "s|^Environment=\"OPENSSL_CONF=.*|Environment=\"OPENSSL_CONF=${INSTALL_DIR}/etc/conf/custom_openssl.cnf\"|g" \
        -e "s|^ExecStart=.*|ExecStart=${PYTHON_PATH} -m orchestrate.start|g" \
        "$SERVICE_FILE" > "$TEMP_SERVICE"

    cp "$TEMP_SERVICE" "${SYSTEMD_DIR}/${SERVICE_NAME}.service"
    rm -f "$TEMP_SERVICE"

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"

    echo -e "${GREEN}Service installed successfully!${NC}"
    echo "Service file: ${SYSTEMD_DIR}/${SERVICE_NAME}.service"
    echo "Use 'systemctl start $SERVICE_NAME' to start the service"
}

uninstall_service() {
    check_root
    load_config

    systemctl stop "$SERVICE_NAME" 2>/dev/null
    systemctl disable "$SERVICE_NAME" 2>/dev/null
    rm -f "${SYSTEMD_DIR}/${SERVICE_NAME}.service"
    systemctl daemon-reload

    echo -e "${GREEN}Service uninstalled successfully!${NC}"

    if [ -d "$INSTALL_DIR" ]; then
        read -p "Remove installation directory $INSTALL_DIR? (y/n): " choice
        if [ "$choice" = "y" ] || [ "$choice" = "Y" ]; then
            rm -rf "$INSTALL_DIR"
            echo "Installation directory removed"
        fi
    fi
}

case "$1" in
    install)
        install_service "$@"
        ;;
    uninstall)
        uninstall_service
        ;;
    status)
        systemctl status "$SERVICE_NAME"
        ;;
    start)
        check_root
        systemctl start "$SERVICE_NAME"
        echo -e "${GREEN}Service started${NC}"
        ;;
    stop)
        check_root
        systemctl stop "$SERVICE_NAME"
        echo -e "${GREEN}Service stopped${NC}"
        ;;
    restart)
        check_root
        systemctl restart "$SERVICE_NAME"
        echo -e "${GREEN}Service restarted${NC}"
        ;;
    enable)
        check_root
        systemctl enable "$SERVICE_NAME"
        echo -e "${GREEN}Service enabled${NC}"
        ;;
    disable)
        check_root
        systemctl disable "$SERVICE_NAME"
        echo -e "${GREEN}Service disabled${NC}"
        ;;
    *)
        usage
        ;;
esac
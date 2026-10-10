#!/bin/bash
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
umask 077

if [ "$#" -eq 0 ]; then set -- serve; fi
if [ "$1" = serve ] && [ "$#" -ne 1 ]; then
    echo "serve accepts no arguments; use runtime configuration/environment" >&2
    exit 2
fi
APP_HOME="${APP_HOME:-/opt/orchestration-center}"
cd "$APP_HOME"
export PATH="/opt/venv/bin:$PATH"

# Python consumes deployment environment directly, including PORT precedence.
# Never rewrite server.conf, database connections, .env, or credential files.
MODELS_CONF="${LLM_CONFIG_FILE:-etc/config/models.yaml}"
LEGACY_MODELS_CONF="common/config/models.yaml"
if [ -f "$MODELS_CONF" ]; then
    echo "Using configured model definitions"
elif [ -z "${LLM_CONFIG_FILE:-}" ] && [ -f "$LEGACY_MODELS_CONF" ]; then
    echo "Using legacy model definitions; migrate mount to etc/config/models.yaml" >&2
elif [ -n "${LLM_CONFIG_FILE:-}" ]; then
    echo "LLM_CONFIG_FILE does not exist" >&2
    exit 1
elif [ -n "${LLM_CHAT_MODEL:-}" ] && [ -n "${LLM_CHAT_URL:-}" ]; then
    case "${LLM_CHAT_PROVIDER:-openai_compatible}" in
        openai|openai_compatible) ;;
        *) echo "provide a complete models.yaml for this model protocol" >&2; exit 1 ;;
    esac
    mkdir -p "$(dirname "$MODELS_CONF")"
    export LLM_CONFIG_FILE="$MODELS_CONF"
    python3 -c '
import os, yaml
chat = {"provider": "openai_compatible", "model": os.environ["LLM_CHAT_MODEL"], "url": os.environ["LLM_CHAT_URL"]}
if os.environ.get("LLM_CHAT_API_KEY"):
    chat["api_key_env"] = "LLM_CHAT_API_KEY"
with open(os.environ["LLM_CONFIG_FILE"], "w", encoding="utf-8") as stream:
    yaml.safe_dump({"models": {"chat": chat}}, stream, sort_keys=False)
'
elif [ -n "${LLM_CHAT_MODEL:-}" ] || [ -n "${LLM_CHAT_URL:-}" ] || [ -n "${LLM_CHAT_API_KEY:-}" ]; then
    echo "Incomplete chat model configuration: set both LLM_CHAT_MODEL and LLM_CHAT_URL" >&2
    exit 1
fi
mkdir -p log run data
if [ "$1" = serve ]; then exec python3 -m orchestrate.start; fi
exec "$@"

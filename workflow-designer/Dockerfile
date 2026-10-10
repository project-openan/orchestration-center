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

# Workflow Designer (frontend) Container Image
# Multi-stage build: compile the Vite app, then serve the static bundle via
# nginx, which also reverse-proxies /api/orchestrate/ to the
# orchestration-center backend (see src/service/api.js's defaultGateway and
# the README's documented Nginx-gateway production mode).
#
# Build:
#   docker build -t workflow-designer:latest .
#
# Run (standalone, expects a reachable "orchestration-center" host):
#   docker run -p 3003:80 workflow-designer:latest

FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY 15-openan-backend.envsh /docker-entrypoint.d/15-openan-backend.envsh
RUN sed -i 's/\r$//' /docker-entrypoint.d/15-openan-backend.envsh \
    && chmod 0755 /docker-entrypoint.d/15-openan-backend.envsh

ENV BACKEND_HOST=orchestration-center \
    BACKEND_PORT=5001 \
    BACKEND_SCHEME=auto \
    ORCH_ENABLE_HTTPS=false \
    BACKEND_VERIFY_SERVER=true

EXPOSE 80

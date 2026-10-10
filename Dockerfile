# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
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

# OpenAN Orchestration Center Container Image
# Multi-stage build for OpenShift / Kubernetes / Cloud Run deployment.
#
# Build:
#   docker build -t orchestration-center:latest .
#
# Run (local, file persistence):
#   See docs/transport-runtime.md for required credentials.
#
# Run (local, PostgreSQL):
#   docker run -e PERSISTENCE_MODE=postgresql \
#     -e DB_HOST=host -e DB_USERNAME=user -e DB_PASSWORD=pass \
#     -p 5001:5001 orchestration-center:latest

FROM python:3.12-slim AS builder

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt

RUN python3 -m venv /opt/venv --copies \
    && . /opt/venv/bin/activate \
    && pip install --no-cache-dir --default-timeout=180 --retries=10 -r /tmp/requirements.txt \
    && rm -rf /tmp/requirements.txt /root/.cache/pip

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends bash libpq5 curl && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    ORCH_IP=0.0.0.0 \
    ORCH_PORT=5001 \
    ORCH_ENABLE_HTTPS=false \
    ORCH_FORWARDED_ALLOW_IPS="127.0.0.1" \
    PERSISTENCE_MODE=file

COPY orchestrate/ /opt/orchestration-center/orchestrate/
COPY samples/solution_packages/ /opt/orchestration-center/samples/solution_packages/
COPY host_agent/ /opt/orchestration-center/host_agent/
COPY common/ /opt/orchestration-center/common/
COPY database/ /opt/orchestration-center/database/
COPY bin/ /opt/orchestration-center/bin/
COPY etc/conf/server.conf.example /opt/orchestration-center/etc/conf/server.conf
COPY etc/conf/server.properties etc/conf/log_config.conf /opt/orchestration-center/etc/conf/
COPY etc/conf/db/ /opt/orchestration-center/etc/conf/db/
COPY etc/config/models.yaml.example /opt/orchestration-center/etc/config/models.yaml.example
COPY docker-entrypoint.sh /opt/orchestration-center/docker-entrypoint.sh

RUN useradd --uid 10001 -m appuser \
    && mkdir -p /opt/orchestration-center/log /opt/orchestration-center/run /opt/orchestration-center/data \
    && mkdir -p /opt/orchestration-center/etc/ssl \
    && sed -i 's/\r$//' /opt/orchestration-center/bin/*.sh /opt/orchestration-center/docker-entrypoint.sh \
    && chmod +x /opt/orchestration-center/bin/*.sh /opt/orchestration-center/docker-entrypoint.sh \
    && chmod 0700 /opt/orchestration-center/etc/ssl  \
    && chown -R appuser:appuser /opt/orchestration-center /opt/venv

WORKDIR /opt/orchestration-center

USER appuser

EXPOSE 5001

ENTRYPOINT ["/opt/orchestration-center/docker-entrypoint.sh"]
CMD ["serve"]

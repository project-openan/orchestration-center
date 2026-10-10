# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Isolated real-network PostgreSQL API test server; never uses local DB settings."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("TESTING", None)

from common.util import config_util

conf = {}
config_util.load_configs(str(Path(__file__).resolve().parents[1] / "etc/conf/server.conf.example"), conf)
config_util.load_configs(str(Path(__file__).resolve().parents[1] / "etc/conf/server.properties"), conf)
os.environ["ORCH_API_TOKEN"] = "test-only-sql-machine-token-000000000000000"
conf.update(persistence_mode="postgresql", ip="127.0.0.1", port=sys.argv[1],
            enable_https="true" if len(sys.argv) > 2 else "false")
conf["auth.register.enabled"] = "true"
conf["external.auth.mode"] = "bearer"
conf["verify_client"] = "false"
config_util.get_conf = lambda: conf

from database.utils import db_connection

# Bypass etc/conf/db_config.json: seed the parsed-config cache and re-arm the
# one-shot database-existence check, exactly as the live tests do.
db_connection._ConnInfoHolder._instance = json.loads(os.environ["OC_POSTGRES_SMOKE_CONFIG"])
conf["connection_config"] = json.loads(os.environ["OC_POSTGRES_SMOKE_CONFIG"])
db_connection._database_verified = False

from database.utils.table_creation import create_tables
from database.utils.user_store import seed_admin_if_empty
from orchestrate import start

create_tables()
seed_admin_if_empty("SmokeAdmin9!")
if len(sys.argv) > 2:
    # Only replace the TLS transport launcher; start.main still runs the real
    # mode validation, security preflight, table init and user bootstrap.
    import uvicorn

    class TLSServer:
        def __init__(self, *_):
            pass

        def run(self):
            uvicorn.run(start.app, host="127.0.0.1", port=int(sys.argv[1]),
                        ssl_certfile=sys.argv[2], ssl_keyfile=sys.argv[3],
                        log_level="warning")

    start.CustomUvicornServer = TLSServer
    start.get_conf_singleton = lambda: None
    start.CertValidator = lambda _: type("Result", (), {
        "validate": lambda _: type("Validation", (), {"is_valid": True})(),
    })()
    start.set_ssl_folder_permissions = lambda: None

start.main()

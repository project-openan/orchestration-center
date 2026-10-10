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

import atexit
import os
import ssl
import sys

import uvicorn
from loguru import logger
from uvicorn import config

from common.cert.cert_validator import CertValidator
from common.config import TLS_CIPHER, FORWARDED_ALLOW_IPS, CONN_TIMEOUT
from common.log.audit_logger import audit_logger, OperationObject, OperationName, LogLevel, OperationResult
from common.util.cipher_converter import CipherConverter
from common.util.cipher_util import DEFAULT_ENCODING
from common.util.conf_util import get_conf_singleton, set_ssl_folder_permissions, load_cert_password
from common.util.config_util import get_conf
from common.util.persistence_mode import validate_storage_mode
from orchestrate.persistence import build_context, configure_context, current_context
from orchestrate.server.frontend_support_server import app
from orchestrate.server.security_preflight import SecurityPreflightError, security_preflight

def seed_admin_if_empty(default_password):
    """Bootstrap through the bound user port, not the process-global SQL helper."""
    users = current_context().users
    if users.has_any():
        return False
    return users.create("admin", default_password, "admin", True)


def customized_create_ssl_context(certfile: str | os.PathLike[str],
                                  keyfile: str | os.PathLike[str] | None,
                                  password: str | None,
                                  ssl_version: int,
                                  cert_reqs: int,
                                  ca_certs: str | os.PathLike[str] | None,
                                  ciphers: str | None,
                                  alpn_protocols: list[str] | None = None) -> ssl.SSLContext:
    """
    Create a custom SSL context for secure connections.

    Args:
        certfile: Path to the certificate file
        keyfile: Path to the private key file (optional)
        password: Password for the private key (optional)
        ssl_version: SSL version to use
        cert_reqs: Certificate verification requirements
        ca_certs: Path to CA certificates file (optional)
        ciphers: Cipher suites to use (optional)
        alpn_protocols: ALPN protocol list advertised by the server,
            passed by uvicorn >= 0.53 (optional)

    Returns:
        SSLContext: Configured SSL context

    Raises:
        Exception: If SSL context creation fails
    """
    try:
        ctx = ssl.SSLContext(ssl_version)
        get_password = (lambda: password) if password else None
        ctx.load_cert_chain(certfile, keyfile, get_password)
        ctx.verify_mode = ssl.VerifyMode(cert_reqs)
        if ca_certs:
            ctx.load_verify_locations(ca_certs)
            if len(get_conf_singleton().get_crl_list()) > 0:
                ctx.load_verify_locations(get_conf_singleton().ssl_crl_file)
                ctx.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF
        if ciphers:
            ctx.set_ciphers(ciphers)
        if alpn_protocols:
            ctx.set_alpn_protocols(alpn_protocols)
        return  ctx
    except Exception as e:
        logger.error(f"customized_create_ssl_context error: {e}")
        raise

def get_user_info_from_env():
    """
    Retrieve user information from environment variables.

    Returns:
        dict: Dictionary containing username, uid, and gid
    """
    user_info = {
        "username":os.environ.get("APP_USER", "unknown"),
        "uid":os.environ.get("APP_UID", "unknown"),
        "gid":os.environ.get("APP_GID", "unknown"),
    }
    return user_info

def record_startup_log():
    """
    Record server startup audit log.
    """
    server_config = get_conf()
    audit_logger.audit({
        'object_name': OperationObject.SERVER,
        'operation_name': OperationName.START_SERVER,
        'level': LogLevel.DANGER,
        'result': OperationResult.SUCCESS,
        'details': {"ip": server_config.get('ip', ""), "port": server_config.get('port', "")},
        'user_name': get_user_info_from_env().get('username'),
    })

config.create_ssl_context = customized_create_ssl_context

class CustomUvicornServer:
    """
    Custom Uvicorn server with SSL configuration.
    """
    def __init__(self, server_config, conf_obj):
        """
        Initialize the custom Uvicorn server.

        Args:
            server_config: Server configuration dictionary
            conf_obj: Configuration object containing SSL settings
        """
        self.server_config = server_config
        self.conf_obj = conf_obj

    def run(self):
        """
        Start the Uvicorn server with SSL configuration.
        """
        os.environ["FORWARDED_ALLOW_IPS"] = self.server_config.get(FORWARDED_ALLOW_IPS, "127.0.0.1")
        server_config = uvicorn.Config(
            app=app,
            host=self.server_config.get('ip', "127.0.0.1"),
            port=int(self.server_config.get('port', 5001)),
            ssl_certfile=self.conf_obj.ssl_certfile,
            ssl_keyfile=self.conf_obj.ssl_keyfile,
            ssl_keyfile_password=load_cert_password(self.conf_obj.ssl_keyfile_password).decode(DEFAULT_ENCODING),
            ssl_ca_certs=self.conf_obj.ssl_ca_certs if self.conf_obj.verify_client != ssl.CERT_NONE else None,
            ssl_cert_reqs=self.conf_obj.verify_client,
            ssl_ciphers=CipherConverter.convert(self.server_config.get(TLS_CIPHER)),
            timeout_keep_alive=5,
            timeout_graceful_shutdown=2,
            log_level="info",
            proxy_headers=True
        )
        server = uvicorn.Server(server_config)
        record_startup_log()
        server.run()

def initialize_storage(server_config):
    """Build the configured storage backend and make it usable.

    This is the composition root: the one place that decides which backend the
    process runs on. Keeping the order explicit and testable matters, because
    it must stay after the security preflight, exactly like the previous
    ``create_tables()`` call: prove the backend is reachable, then create or
    migrate the schema, then bootstrap the first operator account.

    Returns the :class:`~orchestrate.persistence.StorageContext` so the caller
    can close it on shutdown.
    """
    storage = build_context(conf=server_config)
    configure_context(storage)
    storage.check_ready()
    storage.initialize()
    if storage.has_users:
        # Seed the default admin user if the users table is empty. user_store
        # hashes the real plaintext password server-side (see #9), so this is
        # passed as-is rather than pre-hashed.
        if seed_admin_if_empty("OpenAN@2026"):
            logger.info("Default admin user 'admin' created; a password change is required on first login")
        else:
            logger.info("Users already exist, skipping admin seed")
    else:
        logger.info(f"Storage mode '{storage.mode}' has no user store; skipping admin seed")
    return storage


def main():
    """
    Main entry point for starting the PSOP server.
    """
    server_config = get_conf()
    is_https = server_config.get("enable_https", True)
    is_enable_https = str(is_https).lower() == 'true'
    validate_storage_mode()
    try:
        preflight = security_preflight(server_config)
    except SecurityPreflightError as e:
        logger.error(str(e))
        sys.exit(str(e))
    for message in preflight.warnings:
        logger.warning(message)
    if preflight.dev_insecure_mode:
        audit_logger.audit({
            'object_name': OperationObject.SERVER,
            'operation_name': OperationName.START_SERVER,
            'level': LogLevel.DANGER,
            'result': OperationResult.SUCCESS,
            'details': {
                "ip": server_config.get('ip', ""),
                "port": server_config.get('port', ""),
                "dev_insecure_mode": True,
            },
            'user_name': get_user_info_from_env().get('username'),
        })
    storage = initialize_storage(server_config)
    atexit.register(storage.close)
    if not is_enable_https:
        uvicorn.run(app, host=server_config.get('ip', "127.0.0.1"), port=int(server_config.get('port', 5001)),
                    forwarded_allow_ips=server_config.get(FORWARDED_ALLOW_IPS, "127.0.0.1"),
                    timeout_graceful_shutdown=2)
    else:
        try:
            conf_obj = get_conf_singleton()
            result = CertValidator(conf_obj).validate()
            if not result.is_valid:
                sys.exit(result.message)
            set_ssl_folder_permissions()
            server = CustomUvicornServer(server_config, conf_obj)
            server.run()
        except Exception as e:
            logger.error(f"server start failed {e}")
            audit_logger.audit({
                'object_name': OperationObject.SERVER,
                'operation_name': OperationName.START_SERVER,
                'level': LogLevel.DANGER,
                'result': OperationResult.FAILURE,
                'details': {"ip": server_config.get('ip', ""), "port": server_config.get('port', "")},
                'user_name': get_user_info_from_env().get('username'),
            })
            sys.exit(f"server start failed {e}")

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("  Orchestration Center Interfaces")
    logger.info("=" * 50)
    logger.info("  [Internal API - /rest/v1/orchestrate]")
    logger.info("  POST /parse-pdf              - Upload SolutionPackage PDF")
    logger.info("  POST /generate-from-preflow  - SOP text -> PSOP")
    logger.info("  POST /generate-from-intent   - Intent -> PSOP")
    logger.info("  POST /retrieve-by-intent     - Semantic PSOP search")
    logger.info("  GET  /execute?psop_id=<id>   - Execute PSOP (SSE)")
    logger.info("  CRUD /workflows              - PSOP lifecycle")
    logger.info("  GET  /agent-cards            - Agent inventory")
    logger.info("  CRUD /execution-records      - Execution history")
    logger.info("")
    logger.info("  [External API - /api/v1]")
    logger.info("  POST /api/v1/orchestrate/sop         - SOP orchestration (text or PDF/TXT/MD file)")
    logger.info("  POST /api/v1/orchestrate/intent      - Intent orchestration")
    logger.info("  POST /api/v1/orchestrate/search      - Search workflows by intent")
    logger.info("  POST /api/v1/orchestrate/execute     - Auto-orchestrate + execute (SSE)")
    logger.info("  GET  /api/v1/orchestrate/execute/{id} - Execute known PSOP (SSE)")
    logger.info("  GET  /api/v1/executions/{id}         - Get execution result")
    logger.info("")
    logger.info("  For detailed documentation, refer to: Orchestration Center API Reference")
    logger.info("=" * 50)
    main()

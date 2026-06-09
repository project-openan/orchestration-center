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

import os
import ssl
import sys

import uvicorn
from loguru import logger
from uvicorn import config

from common.cert.cert_validater import CertValidator
from common.config import TLS_CIPHER, FORWARDED_ALLOW_IPS, CONN_TIMEOUT
from common.log.audit_logger import audit_logger, OperationObject, OperationName, LogLevel, OperationResult
from common.util.cipher_converter import CipherConverter
from common.util.cipher_util import DEFAULT_ENCODING
from common.util.conf_util import conf_singleton_obj, set_ssl_folder_permissions, load_cert_password
from common.util.config_util import get_conf
from database.utils.table_creation import create_tables
from orchestrate.server.frontend_support_server import app

def customized_create_ssl_context(certfile: str | os.PathLike[str],
                                  keyfile: str | os.PathLike[str] | None,
                                  password: str | None,
                                  ssl_version: int,
                                  cert_reqs: int,
                                  ca_certs: str | os.PathLike[str] | None,
                                  ciphers: str | None) -> ssl.SSLContext:
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
            if len(conf_singleton_obj.get_crl_list()) > 0:
                ctx.load_verify_locations(conf_singleton_obj.ssl_crl_file)
                ctx.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF
        if ciphers:
            ctx.set_ciphers(ciphers)
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
            ssl_ca_certs=self.conf_obj.ssl_ca_certs,
            ssl_cert_reqs=self.conf_obj.verify_client,
            ssl_ciphers=CipherConverter.convert(self.server_config.get(TLS_CIPHER)),
            timeout_keep_alive=0,
            timeout_graceful_shutdown=int(self.server_config.get(CONN_TIMEOUT, 30)),
            log_level="info",
            proxy_headers=True
        )
        server = uvicorn.Server(server_config)
        record_startup_log()
        server.run()


def main():
    """
    Main entry point for starting the PSOP server.
    """
    server_config = get_conf()
    is_https = server_config.get("enable_https", True)
    is_enable_https = str(is_https).lower() == 'true'
    if server_config.get('persistence_mode', 'file').lower() != 'file':
        create_tables()
    if not is_enable_https:
        uvicorn.run(app, host=server_config.get('ip', "127.0.0.1"), port=int(server_config.get('port', 5001)))
    else:
        try:
            conf_obj = conf_singleton_obj
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
    logger.info("  For detailed documentation, refer to: PSOP_API_DOCUMENTATION.md")
    logger.info("=" * 50)
    main()

# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Local probe using configured TLS, never insecure certificate bypass."""
import os
import ssl
from pathlib import Path
from urllib.request import ProxyHandler, HTTPSHandler, build_opener
from common.util.config_util import get_conf, get_root_path

def _path(value):
    path = Path(value)
    return str(path if path.is_absolute() else Path(get_root_path()) / path)

def probe():
    conf = get_conf()
    secure = str(conf.get("enable_https", "true")).lower() == "true"
    host = os.environ.get("ORCH_HEALTHCHECK_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT") or conf.get("port", 5001))
    handlers = [ProxyHandler({})]
    if secure:
        context = ssl.create_default_context(cafile=_path(conf.get("ssl_ca_certs", "etc/ssl/trust.cer")))
        cert = os.environ.get("ORCH_HEALTHCHECK_CLIENT_CERT")
        key = os.environ.get("ORCH_HEALTHCHECK_CLIENT_KEY")
        if str(conf.get("verify_client", "true")).lower() == "true" and not (cert and key):
            raise ValueError("mTLS probe requires ORCH_HEALTHCHECK_CLIENT_CERT and CLIENT_KEY")
        if cert:
            context.load_cert_chain(_path(cert), _path(key) if key else None)
        handlers.append(HTTPSHandler(context=context))
    authority = f"[{host}]" if ":" in host else host
    url = f"{'https' if secure else 'http'}://{authority}:{port}/health"
    with build_opener(*handlers).open(url, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"Health probe returned HTTP {response.status}")

if __name__ == "__main__":
    probe()

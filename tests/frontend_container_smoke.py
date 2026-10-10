# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Exercise the production nginx entrypoint and real HTTP/HTTPS proxy sockets."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]


def command(*args, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=900)
    if check and result.returncode:
        raise RuntimeError(result.stdout[-3000:] + result.stderr[-3000:])
    return result


BACKEND = """
import http.server, json, os, ssl
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({'path': self.path, 'authorization': self.headers.get('Authorization')}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
server = http.server.ThreadingHTTPServer(('0.0.0.0', 5001), Handler)
if os.environ.get('HTTPS') == 'true':
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('/pki/trust.cer', '/pki/key.pem')
    server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
"""


def run():
    if os.name == "nt" or not shutil.which("docker"):
        raise SystemExit("Requires Linux Docker; run the frontend-container CI job.")
    image = f"openan-frontend-smoke:{os.getpid()}"
    network = f"openan-frontend-smoke-{os.getpid()}"
    containers = []
    with tempfile.TemporaryDirectory(prefix="openan-frontend-") as directory:
        fixture = Path(directory)
        (fixture / "backend.py").write_text(BACKEND, encoding="utf-8")
        command("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                "-subj", "/CN=orchestration-center", "-addext", "subjectAltName=DNS:orchestration-center",
                "-keyout", str(fixture / "key.pem"), "-out", str(fixture / "trust.cer"))
        try:
            command("docker", "build", "-t", image, str(ROOT / "workflow-designer"))
            command("docker", "network", "create", network)
            for secure in (False, True):
                backend = command("docker", "run", "-d", "--network", network,
                                  "--network-alias", "orchestration-center",
                                  "-v", f"{fixture}:/pki:ro", "-e", f"HTTPS={str(secure).lower()}",
                                  "python:3.12-slim", "python", "/pki/backend.py").stdout.strip()
                containers.append(backend)
                args = ["docker", "run", "-d", "--network", network, "-p", "127.0.0.1::80",
                        "-e", f"ORCH_ENABLE_HTTPS={str(secure).lower()}"]
                if secure:
                    args += ["-v", f"{fixture}:/etc/nginx/backend-tls:ro",
                             "-e", "BACKEND_CA_FILE=/etc/nginx/backend-tls/trust.cer"]
                frontend = command(*args, image).stdout.strip()
                containers.append(frontend)
                address = command("docker", "port", frontend, "80/tcp").stdout.strip()
                opener = build_opener(ProxyHandler({}))
                request = Request(f"http://{address}/api/orchestrate/probe",
                                  headers={"Authorization": "Bearer synthetic-proxy-token"})
                deadline = time.monotonic() + 30
                while True:
                    try:
                        with opener.open(request, timeout=3) as response:
                            result = json.load(response)
                        assert result == {"path": "/probe", "authorization": "Bearer synthetic-proxy-token"}
                        break
                    except URLError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError(command("docker", "logs", frontend).stdout[-3000:])
                        time.sleep(0.2)
                config = command("docker", "exec", frontend, "nginx", "-T").stdout
                assert f"proxy_pass {'https' if secure else 'http'}://orchestration-center:5001/" in config
                if secure:
                    assert "proxy_ssl_verify on;" in config
                command("docker", "rm", "-f", frontend, backend)
                containers.remove(frontend)
                containers.remove(backend)
            rejected = command("docker", "run", "--rm", "-e", "ORCH_ENABLE_HTTPS=true",
                               image, "nginx", "-t", check=False)
            assert rejected.returncode != 0
            assert "requires BACKEND_CA_FILE" in rejected.stdout + rejected.stderr
            print("PASS: actual nginx hook, HTTP/HTTPS verified upstream, routing and auth forwarding, missing CA rejection")
        finally:
            for container in containers:
                command("docker", "rm", "-f", container, check=False)
            command("docker", "network", "rm", network, check=False)
            command("docker", "image", "rm", image, check=False)


if __name__ == "__main__":
    run()

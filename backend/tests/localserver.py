"""Tiny local HTTP/HTTPS servers for engine tests (stdlib only, threaded)."""

from __future__ import annotations

import datetime as dt
import ipaddress
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


class Handler(BaseHTTPRequestHandler):
    server_version = "TestServer"
    hits: list[tuple[str, str]]  # set per server

    def log_message(self, *args) -> None:  # silence
        pass

    def _send(self, code: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        self.server.hits.append((self.command, self.path))  # type: ignore[attr-defined]
        target = getattr(self.server, "redirect_target", "")
        path = self.path
        if path == "/ok":
            self._send(200, b"<html><body>Hello Uptivora</body></html>")
        elif path.startswith("/status/"):
            self._send(int(path.rsplit("/", 1)[1]), b"status")
        elif path == "/slow":
            time.sleep(3)
            self._send(200, b"slow")
        elif path == "/redirect/ok":
            self._send(302, headers={"Location": "/ok"})
        elif path == "/redirect/private":
            self._send(302, headers={"Location": "http://10.0.0.1/admin"})
        elif path == "/redirect/internal":
            self._send(302, headers={"Location": "http://intranet.local/"})
        elif path == "/redirect/loop":
            self._send(302, headers={"Location": "/redirect/loop"})
        elif path == "/redirect/see-other":
            self._send(303, headers={"Location": "/ok"})
        elif path == "/redirect/target":
            self._send(301, headers={"Location": target})
        else:
            self._send(404, b"not found")


class LocalServer:
    def __init__(self, tls_dir: Path | None = None) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.hits = []  # type: ignore[attr-defined]
        self.httpd.daemon_threads = True
        self.scheme = "http"
        if tls_dir is not None:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(tls_dir / "cert.pem", tls_dir / "key.pem")
            self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)
            self.scheme = "https"
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def hits(self) -> list[tuple[str, str]]:
        return self.httpd.hits  # type: ignore[attr-defined]

    def set_redirect_target(self, url: str) -> None:
        self.httpd.redirect_target = url  # type: ignore[attr-defined]

    def url(self, host: str, path: str) -> str:
        return f"{self.scheme}://{host}:{self.port}{path}"

    def __enter__(self) -> LocalServer:
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def make_self_signed(directory: Path, hostname: str, days: int = 30) -> dt.datetime:
    """Write cert.pem/key.pem for ``hostname``; returns the certificate's not-after time."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Uptivora Test CA"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Test Root"),
        ]
    )
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    not_after = now + dt.timedelta(days=days)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(not_after)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(hostname), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    (directory / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (directory / "key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return not_after

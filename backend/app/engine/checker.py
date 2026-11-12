"""Executes one website check. Pure I/O + classification; no database access."""

from __future__ import annotations

import asyncio
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from urllib.parse import urljoin, urlsplit

import httpx
from cryptography import x509
from cryptography.x509.oid import NameOID

from app.core.netguard import UnsafeURLError, validate_monitor_url
from app.engine.netclient import MonitorClients
from app.monitors.status_spec import parse_status_spec, status_matches

MAX_REDIRECTS = 5
MAX_BODY_BYTES = 1024 * 1024  # only read when a keyword must be found
REDIRECT_CODES = {301, 302, 303, 307, 308}


@dataclass(frozen=True, slots=True)
class CheckSpec:
    url: str
    method: str = "GET"
    timeout_seconds: int = 10
    expected_status: str = "200-399"
    keyword: str | None = None
    follow_redirects: bool = True
    verify_tls: bool = True
    capture_tls: bool = True


@dataclass(frozen=True, slots=True)
class TlsInfo:
    expires_at: datetime
    issuer: str
    subject: str


@dataclass(slots=True)
class CheckOutcome:
    is_up: bool
    status_code: int | None = None
    response_ms: int | None = None
    error_kind: str | None = None
    error_message: str | None = None
    final_url: str | None = None
    tls: TlsInfo | None = None
    tls_error: str | None = None


class _CheckFailed(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _name_attr(name: x509.Name, oid) -> str | None:
    attrs = name.get_attributes_for_oid(oid)
    return str(attrs[0].value) if attrs else None


def extract_tls(response: httpx.Response) -> TlsInfo | None:
    stream = response.extensions.get("network_stream")
    ssl_object = stream.get_extra_info("ssl_object") if stream is not None else None
    if ssl_object is None:
        return None
    der = ssl_object.getpeercert(binary_form=True)
    if not der:
        return None
    cert = x509.load_der_x509_certificate(der)
    issuer = _name_attr(cert.issuer, NameOID.ORGANIZATION_NAME) or ""
    issuer_cn = _name_attr(cert.issuer, NameOID.COMMON_NAME)
    if issuer_cn and issuer_cn not in issuer:
        issuer = f"{issuer} {issuer_cn}".strip()
    return TlsInfo(
        expires_at=cert.not_valid_after_utc,
        issuer=issuer[:255] or "Unknown issuer",
        subject=(_name_attr(cert.subject, NameOID.COMMON_NAME) or "")[:255],
    )


def _is_tls_error(exc: BaseException) -> bool:
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, ssl.SSLError | ssl.CertificateError):
            return True
        text = str(cur)
        if "CERTIFICATE_VERIFY_FAILED" in text or "SSL" in text or "TLS" in text:
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def _short(exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    return text.replace("\n", " ")[:300]


def _reason(code: int) -> str:
    try:
        return HTTPStatus(code).phrase
    except ValueError:
        return ""


async def _read_body(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
        size += len(chunk)
        if size >= MAX_BODY_BYTES:
            break
    return b"".join(chunks)[:MAX_BODY_BYTES]


async def run_check(clients: MonitorClients, spec: CheckSpec, user_agent: str) -> CheckOutcome:
    """Run one check within ``spec.timeout_seconds`` (total, including all redirects)."""
    started = time.monotonic()
    expected = parse_status_spec(spec.expected_status)
    client = clients.for_monitor(spec.verify_tls)
    outcome = CheckOutcome(is_up=False, final_url=spec.url)
    headers = {"User-Agent": user_agent, "Accept": "*/*", "Cache-Control": "no-cache"}
    method = spec.method

    try:
        async with asyncio.timeout(spec.timeout_seconds):
            url = spec.url
            for hop in range(MAX_REDIRECTS + 1):
                target = validate_monitor_url(url)  # re-validated on EVERY hop
                remaining = max(spec.timeout_seconds - (time.monotonic() - started), 0.1)
                request = client.build_request(
                    method, target.url, headers=headers, timeout=httpx.Timeout(remaining)
                )
                response = await client.send(request, stream=True)
                try:
                    if hop == 0 and target.scheme == "https" and spec.capture_tls:
                        outcome.tls = extract_tls(response)
                    location = response.headers.get("location")
                    if (
                        response.status_code in REDIRECT_CODES
                        and location
                        and spec.follow_redirects
                    ):
                        next_url = urljoin(target.url, location)
                        if target.scheme == "https" and urlsplit(next_url).scheme == "http":
                            raise _CheckFailed(
                                "insecure_redirect",
                                f"Redirect from HTTPS to insecure URL {next_url[:200]}",
                            )
                        if response.status_code == 303:
                            method = "GET"
                        url = next_url
                        continue

                    outcome.final_url = target.url
                    outcome.status_code = response.status_code
                    body = b""
                    if spec.keyword and method == "GET":
                        body = await _read_body(response)
                    outcome.response_ms = int((time.monotonic() - started) * 1000)

                    if not status_matches(response.status_code, expected):
                        raise _CheckFailed(
                            "http_status",
                            f"HTTP {response.status_code} {_reason(response.status_code)} "
                            f"(expected {spec.expected_status})".replace("  ", " "),
                        )
                    if spec.keyword and spec.keyword not in body.decode("utf-8", "replace"):
                        raise _CheckFailed(
                            "keyword_missing",
                            f"Keyword “{spec.keyword[:80]}” not found in the page",
                        )
                    outcome.is_up = True
                    return outcome
                finally:
                    await response.aclose()
            raise _CheckFailed("too_many_redirects", f"More than {MAX_REDIRECTS} redirects")
    except _CheckFailed as exc:
        outcome.error_kind, outcome.error_message = exc.kind, exc.message
    except UnsafeURLError as exc:
        outcome.error_kind = "dns_error" if exc.code in ("dns_error", "dns_timeout") else "blocked"
        outcome.error_message = exc.message
    except (TimeoutError, httpx.TimeoutException):
        outcome.error_kind = "timeout"
        outcome.error_message = f"No response within {spec.timeout_seconds} s"
        outcome.status_code = None
    except httpx.ConnectError as exc:
        if _is_tls_error(exc):
            outcome.error_kind = "tls_error"
            outcome.error_message = f"TLS/SSL error: {_short(exc)}"
            outcome.tls_error = outcome.error_message
        else:
            outcome.error_kind = "connection_error"
            outcome.error_message = f"Connection failed: {_short(exc)}"
    except (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError) as exc:
        outcome.error_kind = "protocol_error"
        outcome.error_message = f"Connection dropped: {_short(exc)}"
    except httpx.HTTPError as exc:
        outcome.error_kind = "http_error"
        outcome.error_message = _short(exc)
    if outcome.response_ms is None and outcome.status_code is not None:
        outcome.response_ms = int((time.monotonic() - started) * 1000)
    return outcome

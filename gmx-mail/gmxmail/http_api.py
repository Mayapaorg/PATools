"""Local JSON API over GmxClient. Bind it to localhost."""

from __future__ import annotations

import base64
import json
import re
import secrets
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from gmxmail.client import GmxClient
from gmxmail.errors import STATUS_FOR_CODE, GmxError

TTL_SECONDS = 45 * 60
MAX_SESSIONS = 20
_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSIONS_LOCK = threading.Lock()

REFERENCE = {
    "python": [
        "GmxClient(email, password)",
        "list_folders()",
        "list_messages(folder='INBOX', limit=25, page=1, unread_only=False)",
        "get_message(uid, folder='INBOX', mark_seen=True)",
        "search(query, folder='INBOX', limit=25)",
        "send(to, subject, body, cc=None, bcc=None)",
        "reply(uid, folder='INBOX', body='', reply_all=False)",
        "set_read(uid, folder='INBOX', read=True)",
        "move(uid, folder, dest)",
        "delete(uid, folder='INBOX')",
        "download_attachment(uid, folder, index)",
    ],
    "cli": [
        "python3 -m gmxmail folders",
        "python3 -m gmxmail list --folder INBOX --limit 20 --unread",
        "python3 -m gmxmail read UID --folder INBOX",
        "python3 -m gmxmail search 'from:ada subject:proof'",
        "python3 -m gmxmail send --to friend@example.com --subject Hello --body 'Hi'",
        "python3 -m gmxmail mark UID --unread",
        "python3 -m gmxmail move UID --folder INBOX --to Archive",
        "python3 -m gmxmail delete UID",
        "python3 -m gmxmail serve",
    ],
}


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"gmxmail bridge on http://{host}:{port}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _drop_all()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle()

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))

    def _handle(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = 0
        if length < 0 or length > 8_000_000:
            self._reply(413, {"error": "Payload too large.", "code": "bad_request"})
            return
        raw = self.rfile.read(length) if length else b""
        try:
            status, payload = dispatch(self.command, self.path, self.headers, raw)
        except Exception:
            traceback.print_exc()
            status, payload = 500, {"error": "The mail bridge hit an unexpected error.", "code": "gmx"}
        self._reply(status, payload)

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def dispatch(method: str, url: str, headers: Any, raw: bytes) -> tuple[int, dict[str, Any]]:
    _sweep()
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    query = parse_qs(parsed.query)
    if method == "GET" and path == "/health":
        return 200, {"ok": True, "service": "gmxmail"}
    if method == "GET" and path == "/v1/reference":
        return 200, REFERENCE
    try:
        body = json.loads(raw.decode("utf-8") or "{}") if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 400, {"error": "Body must be JSON.", "code": "bad_request"}
    if not isinstance(body, dict):
        return 400, {"error": "Body must be a JSON object.", "code": "bad_request"}
    try:
        if method == "POST" and path == "/v1/sessions":
            return 200, _open_session(body)
        token = _bearer(headers)
        if method == "DELETE" and path == "/v1/sessions":
            return 200, _close_session(token)
        client = _client(token)
        if method == "GET" and path == "/v1/folders":
            return 200, {"folders": client.list_folders(), "email": client.email, "hosts": client.hosts}
        if method == "GET" and path == "/v1/messages":
            return 200, client.list_messages(
                _q(query, "folder", "INBOX"),
                limit=int(_q(query, "limit", "25") or 25),
                page=int(_q(query, "page", "1") or 1),
                unread_only=_q(query, "unread", "") in {"1", "true", "yes"},
            )
        if method == "GET" and path == "/v1/search":
            return 200, client.search(
                _q(query, "q", ""),
                _q(query, "folder", "INBOX"),
                limit=int(_q(query, "limit", "25") or 25),
            )
        attachment = re.fullmatch(r"/v1/messages/(\d{1,20})/attachments/(\d{1,3})", path)
        if attachment and method == "GET":
            payload = client.download_attachment(
                attachment.group(1),
                _q(query, "folder", "INBOX"),
                int(attachment.group(2)),
            )
            return 200, {
                "filename": payload["filename"],
                "content_type": payload["content_type"],
                "size": payload["size"],
                "data_base64": base64.b64encode(payload["data"]).decode("ascii"),
            }
        message = re.fullmatch(r"/v1/messages/(\d{1,20})", path)
        if message and method == "GET":
            peek = _q(query, "peek", "") in {"1", "true", "yes"}
            return 200, client.get_message(message.group(1), _q(query, "folder", "INBOX"), mark_seen=not peek)
        flags = re.fullmatch(r"/v1/messages/(\d{1,20})/flags", path)
        if flags and method == "POST":
            return 200, client.set_read(
                flags.group(1),
                str(body.get("folder") or "INBOX"),
                read=bool(body.get("read", True)),
            )
        delete = re.fullmatch(r"/v1/messages/(\d{1,20})/delete", path)
        if delete and method == "POST":
            return 200, client.delete(delete.group(1), str(body.get("folder") or "INBOX"))
        move = re.fullmatch(r"/v1/messages/(\d{1,20})/move", path)
        if move and method == "POST":
            return 200, client.move(
                move.group(1),
                str(body.get("folder") or "INBOX"),
                str(body.get("dest") or ""),
            )
        reply = re.fullmatch(r"/v1/messages/(\d{1,20})/reply", path)
        if reply and method == "POST":
            return 200, client.reply(
                reply.group(1),
                str(body.get("folder") or "INBOX"),
                body=str(body.get("body") or ""),
                reply_all=bool(body.get("reply_all")),
            )
        if method == "POST" and path == "/v1/send":
            return 200, client.send(
                to=body.get("to") or "",
                subject=str(body.get("subject") or ""),
                body=str(body.get("body") or ""),
                cc=body.get("cc"),
                bcc=body.get("bcc"),
                in_reply_to=body.get("in_reply_to") or None,
                references=body.get("references") or None,
            )
    except GmxError as exc:
        return STATUS_FOR_CODE.get(exc.code, 502), {"error": str(exc), "code": exc.code}
    except ValueError:
        return 400, {"error": "A number in that request is not valid.", "code": "bad_request"}
    return 404, {"error": "No such mail route.", "code": "not_found"}


def _open_session(body: dict[str, Any]) -> dict[str, Any]:
    email = str(body.get("email") or "").strip()
    password = str(body.get("password") or "")
    client = GmxClient(email, password)
    try:
        folders = client.list_folders()
    except Exception:
        client.close()
        raise
    with _SESSIONS_LOCK:
        if len(_SESSIONS) >= MAX_SESSIONS:
            client.close()
            raise GmxError("Too many open mail sessions. Disconnect one first.", code="bad_request")
        token = secrets.token_urlsafe(32)
        now = time.time()
        _SESSIONS[token] = {"client": client, "last": now}
    return {"token": token, "email": client.email, "hosts": client.hosts, "folders": folders}


def _close_session(token: str) -> dict[str, Any]:
    with _SESSIONS_LOCK:
        entry = _SESSIONS.pop(token, None)
    if entry:
        entry["client"].close()
    return {"ok": True}


def _client(token: str) -> GmxClient:
    with _SESSIONS_LOCK:
        entry = _SESSIONS.get(token)
        if not entry:
            raise GmxError("Session expired. Connect to GMX again.", code="auth")
        entry["last"] = time.time()
        return entry["client"]


def _bearer(headers: Any) -> str:
    value = ""
    if headers is not None:
        value = headers.get("Authorization", "") if hasattr(headers, "get") else ""
    match = re.fullmatch(r"Bearer\s+([A-Za-z0-9_\-]{20,})", value.strip())
    if not match:
        raise GmxError("Missing session. Connect to GMX again.", code="auth")
    return match.group(1)


def _q(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0]


def _sweep() -> None:
    now = time.time()
    stale: list[Any] = []
    with _SESSIONS_LOCK:
        for token, entry in list(_SESSIONS.items()):
            if now - entry["last"] > TTL_SECONDS:
                stale.append(_SESSIONS.pop(token)["client"])
    for client in stale:
        client.close()


def _drop_all() -> None:
    with _SESSIONS_LOCK:
        entries = list(_SESSIONS.values())
        _SESSIONS.clear()
    for entry in entries:
        entry["client"].close()

"""IMAP/SMTP client for a GMX mailbox."""

from __future__ import annotations

import imaplib
import os
import smtplib
import socket
import threading
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any

from gmxmail.errors import GmxError
from gmxmail.parse import (
    attachment_from_message,
    auth_message,
    build_search,
    clean_err,
    encode_mutf7,
    extract_fetch_pairs,
    imap_quote,
    message_from_fetch,
    quote_plain,
    safe_folder,
    safe_uid,
    scrub,
    servers_for,
    split_addresses,
    summaries_from_fetch,
)

_HEADER_FETCH = "(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT DATE MESSAGE-ID)] BODYSTRUCTURE)"
_ROLE_ORDER = {"inbox": 0, "drafts": 1, "sent": 2, "archive": 3, "junk": 4, "trash": 5, "folder": 6}


class GmxClient:
    """A logged-in GMX mailbox.

    Methods are the API: list folders and messages, read, search, send,
    reply, mark, move, and delete. One instance holds one IMAP connection.
    It is safe to call from several threads; calls run one at a time.
    """

    def __init__(
        self,
        email: str,
        password: str,
        *,
        imap_host: str | None = None,
        smtp_host: str | None = None,
        timeout: float = 30,
    ) -> None:
        address = (email or "").strip()
        if not password:
            raise GmxError("Password is required.", code="bad_request")
        if any(char in address for char in "\r\n\x00 \t") or any(char in password for char in "\r\n\x00"):
            raise GmxError("Email or password contains a character that cannot be sent.", code="bad_request")
        hosts = None
        if not imap_host or not smtp_host:
            hosts = servers_for(address)
        self.email = address
        self.password = password
        self.imap_host = imap_host or hosts["imap_host"]  # type: ignore[index]
        self.imap_port = 993
        self.smtp_host = smtp_host or hosts["smtp_host"]  # type: ignore[index]
        self.smtp_ssl_port = 465
        self.smtp_starttls_port = 587
        self.timeout = timeout
        self.imap: imaplib.IMAP4_SSL | None = None
        self._selected: str | None = None
        self._folders: list[dict[str, Any]] | None = None
        self._lock = threading.RLock()

    def __enter__(self) -> "GmxClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            imap = self.imap
            self.imap = None
            self._selected = None
            self._folders = None
            if imap is None:
                return
            try:
                imap.logout()
            except Exception:
                try:
                    imap.shutdown()
                except Exception:
                    pass

    @property
    def hosts(self) -> dict[str, Any]:
        return {
            "imap_host": self.imap_host,
            "imap_port": self.imap_port,
            "smtp_host": self.smtp_host,
            "smtp_ssl_port": self.smtp_ssl_port,
        }

    def list_folders(self) -> list[dict[str, Any]]:
        with self._lock:
            self._folders = None
            return self._ensure_folders()

    def list_messages(
        self,
        folder: str = "INBOX",
        *,
        limit: int = 25,
        page: int = 1,
        unread_only: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            path, name = self._resolve(safe_folder(folder))
            limit = _clamp(limit, 1, 100)
            page = _clamp(page, 1, 1000)
            criteria = [("UNSEEN", None)] if unread_only else [("ALL", None)]
            return self._page(path, name, criteria, limit, page)

    def search(self, query: str, folder: str = "INBOX", *, limit: int = 25) -> dict[str, Any]:
        with self._lock:
            path, name = self._resolve(safe_folder(folder))
            return self._page(path, name, build_search(query), _clamp(limit, 1, 100), 1)

    def get_message(self, uid: str, folder: str = "INBOX", *, mark_seen: bool = True) -> dict[str, Any]:
        with self._lock:
            uid = safe_uid(uid)
            path, _name = self._resolve(safe_folder(folder))

            def op() -> dict[str, Any]:
                self._select(path)
                typ, data = self.imap.uid("FETCH", uid, "(UID FLAGS BODY.PEEK[])")  # type: ignore[union-attr]
                self._require(typ, data, "Could not read the message")
                message = message_from_fetch(data, path, uid)
                if mark_seen and not message["seen"]:
                    self.imap.uid("STORE", uid, "+FLAGS.SILENT", "(\\Seen)")  # type: ignore[union-attr]
                    message["seen"] = True
                return message

            return self._call(op)

    def send(
        self,
        *,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> dict[str, Any]:
        recipients_to = split_addresses(to)
        recipients_cc = split_addresses(cc)
        recipients_bcc = split_addresses(bcc)
        if not recipients_to:
            raise GmxError("Add at least one recipient.", code="bad_request")
        subject = (subject or "").strip()
        if not subject:
            raise GmxError("Subject is required.", code="bad_request")
        if len(subject) > 998:
            raise GmxError("Subject is too long.", code="bad_request")
        text = body or ""
        if len(text) > 1_000_000:
            raise GmxError("Message is too long.", code="bad_request")
        mail = EmailMessage()
        mail["From"] = self.email
        mail["To"] = ", ".join(recipients_to)
        if recipients_cc:
            mail["Cc"] = ", ".join(recipients_cc)
        mail["Subject"] = subject
        mail["Date"] = formatdate(localtime=True)
        domain = self.email.rsplit("@", 1)[-1]
        mail["Message-ID"] = make_msgid(domain=domain)
        if in_reply_to:
            mail["In-Reply-To"] = str(in_reply_to).strip()[:998]
        if references:
            mail["References"] = str(references).strip()[:2000]
        mail.set_content(text)
        raw = mail.as_bytes()
        everyone = recipients_to + recipients_cc + recipients_bcc
        with self._lock:
            self._smtp_send(raw, everyone)
            saved = self._append_sent(raw)
        return {
            "sent": True,
            "saved_to_sent": saved,
            "message_id": mail["Message-ID"],
        }

    def reply(self, uid: str, folder: str = "INBOX", *, body: str, reply_all: bool = False) -> dict[str, Any]:
        original = self.get_message(uid, folder, mark_seen=True)
        target = original["from"]["email"]
        if not target:
            raise GmxError("That message has no reply address.", code="bad_request")
        cc: list[str] = []
        if reply_all:
            mine = self.email.casefold()
            seen = {target.casefold(), mine}
            extra = []
            for person in original["to"] + original["cc"]:
                addr = person["email"]
                if addr and addr.casefold() not in seen:
                    seen.add(addr.casefold())
                    extra.append(addr)
            cc = extra
        subject = original["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        who = original["from"]["name"] or target
        when = original["date"] or "an earlier date"
        quoted = f"On {when}, {who} wrote:\n\n{quote_plain(original['text'])}"
        text = (body or "").rstrip()
        full = f"{text}\n\n{quoted}" if text else quoted
        message_id = original["message_id"]
        result = self.send(
            to=target,
            cc=cc,
            subject=subject,
            body=full,
            in_reply_to=message_id or None,
            references=message_id or None,
        )
        result["replied_to"] = original["uid"]
        return result

    def set_read(self, uid: str, folder: str = "INBOX", *, read: bool = True) -> dict[str, Any]:
        with self._lock:
            uid = safe_uid(uid)
            path, _name = self._resolve(safe_folder(folder))

            def op() -> dict[str, Any]:
                self._select(path)
                flag = "+FLAGS.SILENT" if read else "-FLAGS.SILENT"
                typ, data = self.imap.uid("STORE", uid, flag, "(\\Seen)")  # type: ignore[union-attr]
                self._require(typ, data, "Could not update the message")
                return {"uid": uid, "folder": path, "seen": read}

            return self._call(op)

    def move(self, uid: str, folder: str, dest: str) -> dict[str, Any]:
        with self._lock:
            uid = safe_uid(uid)
            source, _ = self._resolve(safe_folder(folder))
            target, target_name = self._resolve(safe_folder(dest))

            def op() -> dict[str, Any]:
                self._select(source)
                typ, data = self.imap.uid("MOVE", uid, imap_quote(target))  # type: ignore[union-attr]
                if typ != "OK":
                    copied, copy_data = self.imap.uid("COPY", uid, imap_quote(target))  # type: ignore[union-attr]
                    self._require(copied, copy_data, "Could not move the message")
                    stored, store_data = self.imap.uid("STORE", uid, "+FLAGS.SILENT", "(\\Deleted)")  # type: ignore[union-attr]
                    self._require(stored, store_data, "Could not move the message")
                    self.imap.expunge()  # type: ignore[union-attr]
                self._selected = None
                return {"uid": uid, "folder": source, "dest": target, "dest_name": target_name}

            return self._call(op)

    def delete(self, uid: str, folder: str = "INBOX") -> dict[str, Any]:
        """Move to Trash, or expunge when the message is already there."""
        trash: dict[str, Any] | None = None
        path = ""
        with self._lock:
            uid = safe_uid(uid)
            path, _name = self._resolve(safe_folder(folder))
            trash = self._folder_by_role("trash")
        if trash and trash["path"] != path:
            moved = self.move(uid, folder, trash["path"])
            return {"uid": uid, "folder": path, "trashed": True, "dest": moved["dest"]}
        with self._lock:

            def op() -> dict[str, Any]:
                self._select(path)
                typ, data = self.imap.uid("STORE", uid, "+FLAGS.SILENT", "(\\Deleted)")  # type: ignore[union-attr]
                self._require(typ, data, "Could not delete the message")
                self.imap.expunge()  # type: ignore[union-attr]
                return {"uid": uid, "folder": path, "trashed": False, "expunged": True}

            return self._call(op)

    def download_attachment(self, uid: str, folder: str, index: int) -> dict[str, Any]:
        if index < 0 or index > 50:
            raise GmxError("Attachment index is not valid.", code="bad_request")
        message_bytes = self._raw_message(uid, folder)
        import email as email_lib

        parsed = email_lib.message_from_bytes(message_bytes)
        filename, content_type, raw = attachment_from_message(parsed, index)
        if len(raw) > 5_000_000:
            raise GmxError("That attachment is larger than 5 MB.", code="bad_request")
        return {
            "filename": filename,
            "content_type": content_type,
            "size": len(raw),
            "data": raw,
        }

    def _raw_message(self, uid: str, folder: str) -> bytes:
        with self._lock:
            uid = safe_uid(uid)
            path, _name = self._resolve(safe_folder(folder))

            def op() -> bytes:
                self._select(path)
                typ, data = self.imap.uid("FETCH", uid, "(BODY.PEEK[])")  # type: ignore[union-attr]
                self._require(typ, data, "Could not read the message")
                for _meta, payload in extract_fetch_pairs(data):
                    if payload:
                        return payload
                raise GmxError("That message is no longer in the folder.", code="not_found")

            return self._call(op)

    def _page(
        self,
        path: str,
        name: str,
        criteria: list[tuple[str, str | None]],
        limit: int,
        page: int,
    ) -> dict[str, Any]:
        def op() -> dict[str, Any]:
            self._select(path)
            uids = self._search(criteria)
            total = len(uids)
            newest_first = list(reversed(uids))
            start = (page - 1) * limit
            chunk = newest_first[start : start + limit]
            messages = self._fetch_summaries(chunk, path) if chunk else []
            order = {uid: index for index, uid in enumerate(chunk)}
            messages.sort(key=lambda item: order.get(item["uid"], 0))
            return {
                "folder": path,
                "folder_name": name,
                "total": total,
                "page": page,
                "limit": limit,
                "messages": messages,
            }

        return self._call(op)

    def _fetch_summaries(self, uids: list[str], folder: str) -> list[dict[str, Any]]:
        uid_set = ",".join(uids)
        typ, data = self.imap.uid("FETCH", uid_set, _HEADER_FETCH)  # type: ignore[union-attr]
        self._require(typ, data, "Could not list messages")
        return summaries_from_fetch(data, folder)

    def _search(self, criteria: list[tuple[str, str | None]]) -> list[str]:
        args: list[Any] = []
        needs_utf8 = False
        for key, value in criteria:
            args.append(key)
            if value is None:
                continue
            if any(ord(char) > 127 for char in value):
                needs_utf8 = True
                encoded = value.encode("utf-8").replace(b"\\", b"\\\\").replace(b'"', b'\\"')
                args.append(b'"' + encoded + b'"')
            else:
                args.append(imap_quote(value))
        if needs_utf8:
            typ, data = self.imap.uid("SEARCH", "CHARSET", "UTF-8", *args)  # type: ignore[union-attr]
        else:
            typ, data = self.imap.uid("SEARCH", *args)  # type: ignore[union-attr]
        self._require(typ, data, "Search failed")
        blob = data[0] if data else b""
        if not blob:
            return []
        if isinstance(blob, bytes):
            return [part.decode() for part in blob.split() if part.isdigit()]
        return []

    def _select(self, path: str) -> None:
        assert self.imap is not None
        if self._selected == path and getattr(self.imap, "state", "") == "SELECTED":
            return
        typ, data = self.imap.select(imap_quote(path))
        if typ != "OK":
            self._selected = None
            raise GmxError(
                f"Cannot open that folder. { _detail(data) }".strip(),
                code="not_found",
            )
        self._selected = path

    def _resolve(self, folder: str) -> tuple[str, str]:
        folders = self._ensure_folders()
        folded = folder.casefold()
        for item in folders:
            if item["path"] == folder or item["name"] == folder:
                return item["path"], item["name"]
        for item in folders:
            if item["path"].casefold() == folded or item["name"].casefold() == folded:
                return item["path"], item["name"]
        encoded = encode_mutf7(folder)
        return encoded, folder

    def _ensure_folders(self) -> list[dict[str, Any]]:
        if self._folders is not None:
            return self._folders

        def op() -> list[dict[str, Any]]:
            from gmxmail.parse import parse_list_line

            assert self.imap is not None
            typ, data = self.imap.list('""', "*")
            if typ != "OK":
                raise GmxError(f"Could not list folders. {_detail(data)}".strip(), code="gmx")
            found: list[dict[str, Any]] = []
            seen: set[str] = set()
            for line in data or []:
                item = parse_list_line(line)
                if not item or item["path"] in seen:
                    continue
                if "\\noselect" in [flag.lower() for flag in item["flags"]]:
                    continue
                seen.add(item["path"])
                found.append(
                    {
                        "name": item["name"],
                        "path": item["path"],
                        "role": item["role"],
                        "delimiter": item["delimiter"],
                    }
                )
            if not any(item["role"] == "inbox" or item["name"].casefold() == "inbox" for item in found):
                found.append({"name": "INBOX", "path": "INBOX", "role": "inbox", "delimiter": "/"})
            found.sort(key=lambda item: (_ROLE_ORDER.get(item["role"], 9), item["name"].casefold()))
            self._folders = found
            return found

        return self._call(op)

    def _folder_by_role(self, role: str) -> dict[str, Any] | None:
        for item in self._ensure_folders():
            if item["role"] == role:
                return item
        return None

    def _append_sent(self, raw: bytes) -> bool:
        sent = self._folder_by_role("sent")
        if not sent:
            return False

        def op() -> bool:
            assert self.imap is not None
            typ, _data = self.imap.append(imap_quote(sent["path"]), "\\Seen", None, raw)
            self._selected = None
            return typ == "OK"

        try:
            return bool(self._call(op))
        except GmxError:
            return False

    def _smtp_send(self, raw: bytes, recipients: list[str]) -> None:
        errors: list[str] = []
        try:
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_ssl_port, timeout=self.timeout) as smtp:
                smtp.login(self.email, self.password)
                smtp.sendmail(self.email, recipients, raw)
                return
        except (OSError, smtplib.SMTPException, UnicodeEncodeError) as exc:
            errors.append(scrub(clean_err(exc), [self.password]))
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_starttls_port, timeout=self.timeout) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(self.email, self.password)
                smtp.sendmail(self.email, recipients, raw)
                return
        except (OSError, smtplib.SMTPException, UnicodeEncodeError) as exc:
            errors.append(scrub(clean_err(exc), [self.password]))
        detail = "; ".join(part for part in errors if part)
        lowered = detail.lower()
        if "auth" in lowered or "credential" in lowered or "535" in detail:
            raise GmxError(auth_message(detail or "SMTP authentication failed"), code="auth")
        raise GmxError(f"Could not send the message. {detail}".strip(), code="gmx")

    def _connect(self) -> None:
        old = self.imap
        self.imap = None
        self._selected = None
        self._folders = None
        if old is not None:
            try:
                old.shutdown()
            except Exception:
                pass
        try:
            imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=self.timeout)
        except (OSError, socket.timeout) as exc:
            raise GmxError(
                f"Could not reach {self.imap_host}. Check the network, and that GMX allows external IMAP.",
                code="unavailable",
            ) from exc
        try:
            imap.login(self.email, self.password)
        except UnicodeEncodeError:
            imap._encoding = "utf-8"  # noqa: SLF001 — imaplib only quotes passwords as its encoding
            try:
                imap.login(self.email, self.password)
            except imaplib.IMAP4.error as exc:
                _discard(imap)
                raise GmxError(auth_message(scrub(clean_err(exc), [self.password])), code="auth") from exc
        except imaplib.IMAP4.error as exc:
            _discard(imap)
            raise GmxError(auth_message(scrub(clean_err(exc), [self.password])), code="auth") from exc
        self.imap = imap

    def _call(self, fn):
        last: BaseException | None = None
        for attempt in (1, 2):
            try:
                if self.imap is None:
                    self._connect()
                return fn()
            except GmxError:
                raise
            except (imaplib.IMAP4.abort, OSError, socket.timeout) as exc:
                last = exc
                self.imap = None
                self._selected = None
                if attempt == 2:
                    break
            except imaplib.IMAP4.error as exc:
                detail = scrub(clean_err(exc), [self.password])
                lowered = detail.lower()
                code = "auth" if "auth" in lowered or "login" in lowered else "gmx"
                message = auth_message(detail) if code == "auth" else detail
                raise GmxError(message or "GMX refused the command.", code=code) from exc
        raise GmxError("The connection to GMX dropped. Try again.", code="unavailable") from last

    def _require(self, typ: str, data: Any, what: str) -> None:
        if typ == "OK":
            return
        detail = _detail(data)
        lowered = detail.lower()
        if "auth" in lowered:
            raise GmxError(auth_message(detail), code="auth")
        code = "not_found" if "exist" in lowered or "no matching" in lowered else "gmx"
        raise GmxError(f"{what}. {detail}".strip(), code=code)


def connect(email: str | None = None, password: str | None = None, **kwargs: Any) -> GmxClient:
    """Open a client using arguments or GMX_EMAIL / GMX_PASSWORD."""
    address = (email or os.environ.get("GMX_EMAIL") or "").strip()
    secret = password if password is not None else os.environ.get("GMX_PASSWORD")
    if not address or not secret:
        raise GmxError(
            "Set GMX_EMAIL and GMX_PASSWORD, or pass them to connect().",
            code="bad_request",
        )
    return GmxClient(address, secret, **kwargs)


def _clamp(value: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def _detail(data: Any) -> str:
    if not data:
        return ""
    first = data[-1] if isinstance(data, (list, tuple)) else data
    if isinstance(first, bytes):
        return first.decode("utf-8", errors="replace").strip()
    return str(first).strip()


def _discard(imap: imaplib.IMAP4_SSL) -> None:
    try:
        imap.logout()
    except Exception:
        try:
            imap.shutdown()
        except Exception:
            pass

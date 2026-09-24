"""Pure helpers: hosts, IMAP encoding, header parsing. No network."""

from __future__ import annotations

import binascii
import email
import email.policy
import html as html_lib
import re
from email.header import decode_header
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from gmxmail.errors import GmxError

_EUROPE_NET = {"net", "de", "at", "ch", "eu"}
_AUTH_HINT = (
    " GMX rejected the login. In GMX webmail open Settings, then POP3 & IMAP, "
    "and enable access for external programs. Use the full email address and "
    "the account password (or an application password if sign-in protection is on)."
)


def servers_for(address: str) -> dict[str, Any]:
    """Pick IMAP/SMTP hosts from a GMX address.

    @gmx.de / .net / .at / .ch use the .net servers. @gmx.fr and @gmx.es have
    their own. Everything else GMX (@gmx.com, .us, .co.uk) uses .com.
    """
    if "@" not in address:
        raise GmxError("Enter a full email address.", code="bad_request")
    domain = address.rsplit("@", 1)[-1].strip().lower()
    labels = [part for part in domain.split(".") if part]
    if "gmx" not in labels:
        raise GmxError(
            "Use a GMX address such as name@gmx.com or name@gmx.net.",
            code="bad_request",
        )
    rest = labels[labels.index("gmx") + 1 :]
    region = rest[0] if rest else ""
    if region in _EUROPE_NET:
        stem = "gmx.net"
    elif region == "fr":
        stem = "gmx.fr"
    elif region == "es":
        stem = "gmx.es"
    else:
        stem = "gmx.com"
    return {
        "domain": domain,
        "imap_host": f"imap.{stem}",
        "imap_port": 993,
        "smtp_host": f"mail.{stem}",
        "smtp_ssl_port": 465,
        "smtp_starttls_port": 587,
    }


def encode_mutf7(text: str) -> str:
    """IMAP modified UTF-7 (RFC 3501). ASCII mailbox names stay ASCII."""
    out: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        raw = "".join(buf).encode("utf-16-be")
        b64 = binascii.b2a_base64(raw).decode("ascii").strip().rstrip("=").replace("/", ",")
        out.append("&" + b64 + "-")
        buf.clear()

    for char in text:
        code = ord(char)
        if 0x20 <= code <= 0x7E and char != "&":
            flush()
            out.append(char)
        elif char == "&":
            flush()
            out.append("&-")
        else:
            buf.append(char)
    flush()
    return "".join(out)


def decode_mutf7(text: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "&":
            out.append(text[index])
            index += 1
            continue
        end = text.find("-", index)
        if end == -1:
            out.append(text[index:])
            break
        token = text[index + 1 : end]
        index = end + 1
        if token == "":
            out.append("&")
            continue
        b64 = token.replace(",", "/")
        pad = "=" * ((4 - len(b64) % 4) % 4)
        raw = binascii.a2b_base64(b64 + pad)
        out.append(raw.decode("utf-16-be", errors="replace"))
    return "".join(out)


def imap_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "********")
    return text


def clean_err(exc: BaseException) -> str:
    text = ""
    if exc.args:
        arg = exc.args[0]
        if isinstance(arg, bytes):
            text = arg.decode("utf-8", errors="replace")
        elif isinstance(arg, list) and arg:
            first = arg[0]
            text = first.decode("utf-8", errors="replace") if isinstance(first, bytes) else str(first)
        else:
            text = str(arg)
    else:
        text = str(exc)
    text = text.strip().strip("'\"")
    if text.startswith("b'") or text.startswith('b"'):
        text = text[2:].rstrip("'\"")
    return re.sub(r"\s+", " ", text)[:500]


def auth_message(detail: str) -> str:
    if "external program" in detail:
        return detail
    return detail.rstrip(".") + "." + _AUTH_HINT


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    chunks: list[str] = []
    try:
        parts = decode_header(value)
    except Exception:
        return value
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            chunks.append(chunk)
    return "".join(chunks).strip()


def parse_addresses(value: str | None) -> list[dict[str, str]]:
    decoded = decode_header_value(value)
    if not decoded:
        return []
    found: list[dict[str, str]] = []
    for name, addr in getaddresses([decoded]):
        name = decode_header_value(name)
        addr = (addr or "").strip()
        if not name and not addr:
            continue
        found.append({"name": name, "email": addr})
    return found


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        when = parsedate_to_datetime(value)
    except Exception:
        return None
    if when is None:
        return None
    return when.isoformat()


def html_to_text(source: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", source)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|h[1-6]|li|blockquote)>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    text = html_lib.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    collapsed: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank and collapsed:
                collapsed.append("")
            blank = True
            continue
        collapsed.append(line)
        blank = False
    return "\n".join(collapsed).strip()


def build_search(query: str) -> list[tuple[str, str | None]]:
    """Turn a desk query into IMAP SEARCH keys.

    Supports from:, to:, subject:, unread, and free text (AND-combined).
    """
    import shlex

    raw = (query or "").strip()
    if not raw:
        return [("ALL", None)]
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = raw.split()
    criteria: list[tuple[str, str | None]] = []
    words: list[str] = []
    keys = (("from:", "FROM"), ("to:", "TO"), ("subject:", "SUBJECT"))
    for part in parts:
        low = part.lower()
        if low in {"unread", "unseen", "is:unread"}:
            criteria.append(("UNSEEN", None))
            continue
        if low in {"read", "seen", "is:read"}:
            criteria.append(("SEEN", None))
            continue
        matched = False
        for prefix, imap_key in keys:
            if low.startswith(prefix) and len(part) > len(prefix):
                criteria.append((imap_key, part[len(prefix) :]))
                matched = True
                break
        if not matched:
            words.append(part)
    if words:
        criteria.append(("TEXT", " ".join(words)))
    return criteria or [("ALL", None)]


_ROLE_FLAGS = {
    "\\inbox": "inbox",
    "\\sent": "sent",
    "\\drafts": "drafts",
    "\\trash": "trash",
    "\\junk": "junk",
    "\\archive": "archive",
}
_ROLE_NAMES: list[tuple[str, tuple[str, ...]]] = [
    ("inbox", ("inbox",)),
    ("sent", ("sent", "sent items", "sent messages", "gesendet", "gesendete", "elementos enviados")),
    ("drafts", ("drafts", "draft", "entwürfe", "entwurfe", "entwurf")),
    ("trash", ("trash", "bin", "deleted", "deleted items", "papierkorb")),
    ("junk", ("junk", "spam", "junk-e-mail", "unerwünschte", "unerwuenschte")),
    ("archive", ("archive", "archiv")),
]


def role_for(flags: list[str], name: str) -> str:
    for flag in flags:
        role = _ROLE_FLAGS.get(flag.lower())
        if role:
            return role
    folded = name.casefold()
    for role, names in _ROLE_NAMES:
        for candidate in names:
            if folded == candidate or folded.startswith(candidate + " ") or folded.startswith(candidate + "/"):
                return role
    return "folder"


def parse_list_line(line: bytes | str | None) -> dict[str, Any] | None:
    if line is None:
        return None
    raw = line.encode("latin1") if isinstance(line, str) else bytes(line)
    raw = raw.strip()
    if not raw or raw == b")":
        return None
    flags: list[str] = []
    if raw.startswith(b"("):
        end = raw.find(b")")
        if end == -1:
            return None
        flags = raw[1:end].decode("ascii", errors="replace").split()
        raw = raw[end + 1 :].strip()
    delimiter: str | None
    if raw.upper().startswith(b"NIL"):
        delimiter = None
        raw = raw[3:].strip()
    elif raw.startswith(b'"'):
        match = re.match(br'"((?:\\.|[^"])*)"\s*(.*)$', raw, re.DOTALL)
        if not match:
            return None
        delimiter = match.group(1).decode("ascii", errors="replace").replace('\\"', '"').replace("\\\\", "\\")
        raw = match.group(2).strip()
    else:
        bits = raw.split(None, 1)
        if len(bits) < 2:
            return None
        delimiter = bits[0].decode("ascii", errors="replace")
        raw = bits[1].strip()
    if raw.startswith(b'"'):
        match = re.match(br'"((?:\\.|[^"])*)"\s*$', raw, re.DOTALL)
        if not match:
            return None
        encoded = match.group(1).decode("ascii", errors="replace").replace('\\"', '"').replace("\\\\", "\\")
    elif raw.startswith(b"{") or not raw:
        return None
    else:
        encoded = raw.decode("ascii", errors="replace")
    name = decode_mutf7(encoded)
    return {
        "name": name,
        "path": encoded,
        "delimiter": delimiter,
        "flags": flags,
        "role": role_for(flags, name),
    }


def parse_fetch_meta(meta: bytes) -> dict[str, Any]:
    uid_match = re.search(rb"\bUID (\d+)", meta)
    flags_match = re.search(rb"FLAGS \(([^)]*)\)", meta)
    size_match = re.search(rb"RFC822\.SIZE (\d+)", meta)
    flags = flags_match.group(1).decode("ascii", errors="replace").split() if flags_match else []
    return {
        "uid": uid_match.group(1).decode() if uid_match else "",
        "flags": flags,
        "seen": any(flag.lower() == "\\seen" for flag in flags),
        "answered": any(flag.lower() == "\\answered" for flag in flags),
        "size": int(size_match.group(1)) if size_match else 0,
    }


def extract_fetch_pairs(data: Any) -> list[tuple[bytes, bytes | None]]:
    pairs: list[tuple[bytes, bytes | None]] = []
    if not data:
        return pairs
    for item in data:
        if item is None:
            continue
        if isinstance(item, tuple):
            meta = item[0] if item and isinstance(item[0], (bytes, bytearray)) else b""
            payload = item[1] if len(item) > 1 and isinstance(item[1], (bytes, bytearray)) else None
            if meta or payload is not None:
                pairs.append((bytes(meta), bytes(payload) if payload is not None else None))
            continue
        if isinstance(item, (bytes, bytearray)):
            raw = bytes(item).strip()
            if raw in (b")", b""):
                continue
            pairs.append((raw, None))
    return pairs


def _header_message(payload: bytes) -> email.message.Message:
    blob = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if not blob.endswith(b"\n"):
        blob += b"\n"
    if b"\n\n" not in blob:
        blob += b"\n"
    return email.message_from_bytes(blob.replace(b"\n", b"\r\n"), policy=email.policy.default)


def summary_from_header(
    meta: bytes,
    payload: bytes | None,
    folder: str,
    structure: str = "",
) -> dict[str, Any] | None:
    parsed = parse_fetch_meta(meta)
    if not parsed["uid"] or payload is None:
        return None
    header = _header_message(payload)
    subject = decode_header_value(header.get("Subject"))
    sender = parse_addresses(header.get("From"))
    media = media_from_bodystructure(structure)
    return {
        "uid": parsed["uid"],
        "folder": folder,
        "from": sender[0] if sender else {"name": "", "email": ""},
        "to": parse_addresses(header.get("To")),
        "cc": parse_addresses(header.get("Cc")),
        "subject": subject or "(no subject)",
        "date": parse_date(header.get("Date")),
        "message_id": (header.get("Message-ID") or "").strip(),
        "seen": parsed["seen"],
        "answered": parsed["answered"],
        "size": parsed["size"],
        "preview": "",
        "has_attachments": bool(media),
        "media": media,
    }


def summaries_from_fetch(data: Any, folder: str) -> list[dict[str, Any]]:
    pairs = extract_fetch_pairs(data)
    found: list[dict[str, Any]] = []
    index = 0
    while index < len(pairs):
        meta, payload = pairs[index]
        blobs = [meta]
        nxt = index + 1
        if payload is not None:
            while nxt < len(pairs) and pairs[nxt][1] is None and b"UID " not in pairs[nxt][0]:
                blobs.append(pairs[nxt][0])
                nxt += 1
        item = summary_from_header(meta, payload, folder, _join_bodystructure(blobs))
        if item:
            found.append(item)
        index = nxt if payload is not None else index + 1
    return found


_SIGNATURES = {
    "application/pkcs7-signature",
    "application/x-pkcs7-signature",
    "application/pgp-signature",
}


def _join_bodystructure(blobs: list[bytes]) -> str:
    text = " ".join(blob.decode("latin-1", errors="replace") for blob in blobs)
    return _slice_bodystructure(text) or ""


def _slice_bodystructure(text: str) -> str | None:
    start = text.upper().find("BODYSTRUCTURE")
    if start < 0:
        return None
    rest = text[start + len("BODYSTRUCTURE") :].lstrip()
    if not rest.startswith("("):
        return None
    depth = 0
    quote = False
    escape = False
    for index, char in enumerate(rest):
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                quote = False
            continue
        if char == '"':
            quote = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return rest[: index + 1]
    return None


def _tokenize_imap(text: str) -> list[Any]:
    tokens: list[Any] = []
    index = 0
    size = len(text)
    while index < size:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "()":
            tokens.append(char)
            index += 1
            continue
        if char == '"':
            index += 1
            buf: list[str] = []
            while index < size:
                if text[index] == "\\" and index + 1 < size:
                    buf.append(text[index + 1])
                    index += 2
                    continue
                if text[index] == '"':
                    index += 1
                    break
                buf.append(text[index])
                index += 1
            tokens.append("".join(buf))
            continue
        if char == "{":
            raise ValueError("literal")
        start = index
        while index < size and not text[index].isspace() and text[index] not in "()":
            index += 1
        atom = text[start:index]
        if atom.upper() == "NIL":
            tokens.append(None)
        elif atom.isdigit() or (atom.startswith("-") and atom[1:].isdigit()):
            tokens.append(int(atom))
        else:
            tokens.append(atom)
    return tokens


def _parse_tokens(tokens: list[Any], index: int = 0) -> tuple[Any, int]:
    if index >= len(tokens):
        raise ValueError("empty")
    token = tokens[index]
    if token != "(":
        return token, index + 1
    items: list[Any] = []
    index += 1
    while index < len(tokens) and tokens[index] != ")":
        value, index = _parse_tokens(tokens, index)
        items.append(value)
    if index >= len(tokens) or tokens[index] != ")":
        raise ValueError("unclosed")
    return items, index + 1


def _param_value(params: Any, key: str) -> str:
    if not isinstance(params, list):
        return ""
    wanted = key.upper()
    index = 0
    while index + 1 < len(params):
        name = params[index]
        value = params[index + 1]
        if isinstance(name, str) and name.upper() == wanted and isinstance(value, str):
            return value
        index += 2
    return ""


def _part_file(node: list[Any]) -> tuple[str, str]:
    filename = (_param_value(node[2], "NAME") or _param_value(node[2], "FILENAME")) if len(node) > 2 else ""
    disposition = ""
    for item in node:
        if (
            isinstance(item, list)
            and item
            and isinstance(item[0], str)
            and item[0].upper() in {"ATTACHMENT", "INLINE"}
        ):
            disposition = item[0].upper()
            if len(item) > 1:
                filename = _param_value(item[1], "FILENAME") or filename
    return disposition, filename


def _collect_media(node: Any, found: list[dict[str, str]]) -> None:
    if not isinstance(node, list) or not node:
        return
    if isinstance(node[0], list):
        for child in node:
            if isinstance(child, list):
                _collect_media(child, found)
            else:
                break
        return
    if not (isinstance(node[0], str) and len(node) > 1 and isinstance(node[1], str)):
        return
    major = node[0].upper()
    minor = node[1].lower()
    if major == "MULTIPART":
        return
    content_type = f"{major.lower()}/{minor}"
    if content_type in _SIGNATURES:
        return
    disposition, filename = _part_file(node)
    if major == "TEXT" and minor in {"plain", "html"} and disposition != "ATTACHMENT" and not filename:
        return
    if major == "MESSAGE" and disposition != "ATTACHMENT" and not filename:
        return
    if major not in {"TEXT", "IMAGE", "AUDIO", "VIDEO", "APPLICATION", "MESSAGE"}:
        return
    found.append({"content_type": content_type, "filename": filename})


def media_from_bodystructure(structure: str) -> list[dict[str, str]]:
    if not structure:
        return []
    try:
        node, _index = _parse_tokens(_tokenize_imap(structure), 0)
    except (ValueError, IndexError, RecursionError):
        return []
    found: list[dict[str, str]] = []
    _collect_media(node, found)
    return found


def _part_text(part: email.message.Message) -> str:
    try:
        content = part.get_content()
        if isinstance(content, str):
            return content
    except Exception:
        pass
    payload = part.get_payload(decode=True) or b""
    if isinstance(payload, str):
        return payload
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def body_and_attachments(message: email.message.Message) -> tuple[str, bool, list[dict[str, Any]]]:
    plain: str | None = None
    html_body: str | None = None
    attachments: list[dict[str, Any]] = []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.is_multipart():
            continue
        disposition = (part.get_content_disposition() or "").lower()
        filename = part.get_filename()
        ctype = part.get_content_type()
        if filename or disposition == "attachment":
            raw = part.get_payload(decode=True) or b""
            if isinstance(raw, str):
                raw = raw.encode("utf-8", errors="replace")
            attachments.append(
                {
                    "index": len(attachments),
                    "filename": filename or f"attachment-{len(attachments) + 1}",
                    "content_type": ctype,
                    "size": len(raw),
                }
            )
            continue
        if ctype == "text/plain" and plain is None:
            plain = _part_text(part)
        elif ctype == "text/html" and html_body is None:
            html_body = _part_text(part)
        elif plain is None and ctype.startswith("text/") and ctype != "text/html":
            plain = _part_text(part)
    if plain and plain.strip():
        return plain.replace("\r\n", "\n").strip(), False, attachments
    if html_body:
        return html_to_text(html_body), True, attachments
    return "", False, attachments


def message_from_fetch(data: Any, folder: str, requested_uid: str) -> dict[str, Any]:
    for meta, payload in extract_fetch_pairs(data):
        parsed = parse_fetch_meta(meta)
        uid = parsed["uid"] or requested_uid
        if payload is None:
            continue
        if payload.lstrip().lower().startswith(b"from:") or payload.lstrip().lower().startswith(b"return-path:") or b"\n" in payload[:400]:
            message = email.message_from_bytes(payload, policy=email.policy.default)
        else:
            continue
        text, from_html, attachments = body_and_attachments(message)
        subject = decode_header_value(message.get("Subject"))
        sender = parse_addresses(message.get("From"))
        preview = re.sub(r"\s+", " ", text).strip()[:180]
        return {
            "uid": uid,
            "folder": folder,
            "from": sender[0] if sender else {"name": "", "email": ""},
            "to": parse_addresses(message.get("To")),
            "cc": parse_addresses(message.get("Cc")),
            "bcc": parse_addresses(message.get("Bcc")),
            "subject": subject or "(no subject)",
            "date": parse_date(message.get("Date")),
            "message_id": (message.get("Message-ID") or "").strip(),
            "seen": parsed["seen"],
            "answered": parsed["answered"],
            "size": parsed["size"] or len(payload),
            "preview": preview,
            "text": text,
            "text_from_html": from_html,
            "attachments": attachments,
            "has_attachments": bool(attachments),
        }
    raise GmxError("That message is no longer in the folder.", code="not_found")


def attachment_from_message(message: email.message.Message, index: int) -> tuple[str, str, bytes]:
    current = 0
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.is_multipart():
            continue
        disposition = (part.get_content_disposition() or "").lower()
        filename = part.get_filename()
        if not filename and disposition != "attachment":
            continue
        if current == index:
            raw = part.get_payload(decode=True) or b""
            if isinstance(raw, str):
                raw = raw.encode("utf-8", errors="replace")
            return filename or f"attachment-{index + 1}", part.get_content_type(), raw
        current += 1
    raise GmxError("Attachment not found.", code="not_found")


def split_addresses(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    chunks: list[str] = []
    items = [value] if isinstance(value, str) else list(value)
    for item in items:
        chunks.extend(re.split(r"[,;]", item))
    found: list[str] = []
    for chunk in chunks:
        address = chunk.strip()
        if not address:
            continue
        if not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", address):
            raise GmxError(f"Invalid email address: {address}", code="bad_request")
        found.append(address)
    return found


def quote_plain(text: str) -> str:
    lines = text.splitlines() or [""]
    return "\n".join(f"> {line}" for line in lines)


def safe_uid(uid: str) -> str:
    if not re.fullmatch(r"\d{1,20}", uid or ""):
        raise GmxError("Message id must be a numeric UID.", code="bad_request")
    return uid


def safe_folder(folder: str) -> str:
    if not folder or len(folder) > 400 or any(char in folder for char in "\r\n\x00"):
        raise GmxError("Folder name is missing or not usable.", code="bad_request")
    return folder

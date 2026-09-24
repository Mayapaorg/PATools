"""Command line for the GMX mailbox API."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from typing import Any

from gmxmail import __version__
from gmxmail.client import GmxClient
from gmxmail.errors import GmxError
from gmxmail.parse import servers_for


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    try:
        if args.command == "hosts":
            print(json.dumps(servers_for(args.address), indent=2))
            return 0
        if args.command == "serve":
            return _serve(args)
        client = _client_from_args(args)
        try:
            payload = _run(client, args)
        finally:
            client.close()
    except GmxError as exc:
        print(f"gmxmail: {exc}", file=sys.stderr)
        return 2 if exc.code == "auth" else 1
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        print("gmxmail: cancelled", file=sys.stderr)
        return 130
    if args.command in {"mark", "delete", "move"} or getattr(args, "json", False) or args.command == "send":
        if not getattr(args, "json", False) and args.command == "send":
            where = " and saved a copy in Sent" if payload.get("saved_to_sent") else ""
            print(f"Sent{where}.")
            return 0
        if not getattr(args, "json", False) and args.command == "mark":
            print("Marked read." if payload["seen"] else "Marked unread.")
            return 0
        if not getattr(args, "json", False) and args.command == "delete":
            print("Moved to Trash." if payload.get("trashed") else "Deleted.")
            return 0
        if not getattr(args, "json", False) and args.command == "move":
            print(f"Moved to {payload.get('dest_name') or payload.get('dest')}.")
            return 0
    if getattr(args, "json", False) or args.command in {"send", "mark", "delete", "move"}:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    _print_human(args, payload)
    return 0


def _run(client: GmxClient, args: argparse.Namespace) -> Any:
    if args.command == "folders":
        return {"folders": client.list_folders()}
    if args.command == "list":
        return client.list_messages(
            args.folder,
            limit=args.limit,
            page=args.page,
            unread_only=args.unread,
        )
    if args.command == "read":
        return client.get_message(args.uid, args.folder, mark_seen=not args.peek)
    if args.command == "search":
        return client.search(args.query, args.folder, limit=args.limit)
    if args.command == "send":
        if args.body is None and args.body_file is None:
            raise GmxError("Pass --body or --body-file.", code="bad_request")
        body = args.body
        if args.body_file:
            body = args.body_file.read()
        return client.send(
            to=args.to or [],
            cc=args.cc or [],
            bcc=args.bcc or [],
            subject=args.subject,
            body=body or "",
        )
    if args.command == "mark":
        return client.set_read(args.uid, args.folder, read=args.read)
    if args.command == "move":
        return client.move(args.uid, args.folder, args.to_folder)
    if args.command == "delete":
        return client.delete(args.uid, args.folder)
    if args.command == "attachment":
        payload = client.download_attachment(args.uid, args.folder, args.index)
        dest = args.out or payload["filename"]
        with open(dest, "wb") as handle:
            handle.write(payload["data"])
        return {"saved": dest, "filename": payload["filename"], "size": payload["size"]}
    raise GmxError(f"Unknown command {args.command}", code="bad_request")


def _print_human(args: argparse.Namespace, payload: Any) -> None:
    if args.command == "folders":
        for folder in payload["folders"]:
            print(f"{folder['role']:<8} {folder['name']}")
        return
    if args.command in {"list", "search"}:
        print(f"{payload['folder_name']}  {payload['total']} message(s)")
        for message in payload["messages"]:
            mark = " " if message["seen"] else "*"
            sender = message["from"]["name"] or message["from"]["email"] or "?"
            when = (message["date"] or "")[:16].replace("T", " ")
            media = _media_label(message)
            suffix = f"  [{media}]" if media else ""
            print(f"{mark} {message['uid']:>6}  {when:<16}  {_clip(sender, 22):<22}  {_clip(message['subject'], 48)}{suffix}")
        return
    if args.command == "read":
        sender = payload["from"]
        print(f"From: {sender['name']} <{sender['email']}>".replace(" <>", ""))
        print("To: " + ", ".join(_fmt_addr(item) for item in payload["to"]))
        if payload["cc"]:
            print("Cc: " + ", ".join(_fmt_addr(item) for item in payload["cc"]))
        print(f"Date: {payload['date'] or ''}")
        print(f"Subject: {payload['subject']}")
        if payload["attachments"]:
            names = ", ".join(item["filename"] for item in payload["attachments"])
            print(f"Attachments: {names}")
        print()
        print(payload["text"])
        return
    if args.command == "attachment":
        print(f"Saved {payload['saved']} ({payload['size']} bytes)")
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _media_label(message: dict[str, Any]) -> str:
    seen: list[str] = []
    for item in message.get("media") or []:
        kind = str(item.get("content_type") or "")
        if kind and kind not in seen:
            seen.append(kind)
    return ", ".join(seen)


def _fmt_addr(item: dict[str, str]) -> str:
    if item["name"] and item["email"]:
        return f"{item['name']} <{item['email']}>"
    return item["email"] or item["name"]


def _clip(text: str, width: int) -> str:
    text = " ".join(text.split())
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


def _client_from_args(args: argparse.Namespace) -> GmxClient:
    email = (args.email or os.environ.get("GMX_EMAIL") or "").strip()
    password = args.password if args.password is not None else os.environ.get("GMX_PASSWORD")
    if not email:
        raise GmxError("Pass --email or set GMX_EMAIL.", code="bad_request")
    if not password:
        if sys.stdin.isatty():
            password = getpass.getpass("GMX password: ")
        else:
            raise GmxError("Pass --password or set GMX_PASSWORD.", code="bad_request")
    return GmxClient(
        email,
        password,
        imap_host=args.imap_host,
        smtp_host=args.smtp_host,
    )


def _serve(args: argparse.Namespace) -> int:
    host = args.host
    if host not in {"127.0.0.1", "localhost", "::1"} and not args.allow_remote:
        print(
            "gmxmail: refusing to listen beyond localhost without --allow-remote",
            file=sys.stderr,
        )
        return 1
    from gmxmail.http_api import serve

    serve(host, args.port)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gmxmail",
        description="Manage a GMX mailbox from the command line. The same actions exist as GmxClient methods.",
    )
    parser.add_argument("--version", action="version", version=f"gmxmail {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--email", help="GMX address. Defaults to GMX_EMAIL.")
    common.add_argument("--password", help="Prefer GMX_PASSWORD so the secret stays out of the process list.")
    common.add_argument("--imap-host", help="Override the IMAP host. SMTP host is then required too if you leave the default.")
    common.add_argument("--smtp-host", help="Override the SMTP host.")
    common.add_argument("--json", action="store_true", help="Print JSON.")
    folder = common.add_argument("--folder", default="INBOX", help="Folder name or IMAP path. Default: INBOX.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("folders", parents=[common], help="List folders.")
    listing = sub.add_parser("list", parents=[common], help="List messages, newest first.")
    listing.add_argument("--limit", type=int, default=25)
    listing.add_argument("--page", type=int, default=1)
    listing.add_argument("--unread", action="store_true")
    reading = sub.add_parser("read", parents=[common], help="Print one message.")
    reading.add_argument("uid")
    reading.add_argument("--peek", action="store_true", help="Do not mark the message read.")
    searching = sub.add_parser("search", parents=[common], help="Search. Supports from:, to:, subject:, unread.")
    searching.add_argument("query")
    searching.add_argument("--limit", type=int, default=25)
    sending = sub.add_parser("send", parents=[common], help="Send a message and keep a copy in Sent when GMX allows it.")
    sending.add_argument("--to", action="append", required=True)
    sending.add_argument("--cc", action="append")
    sending.add_argument("--bcc", action="append")
    sending.add_argument("--subject", required=True)
    sending.add_argument("--body")
    sending.add_argument("--body-file", type=argparse.FileType("r", encoding="utf-8"))
    marking = sub.add_parser("mark", parents=[common], help="Mark a message read or unread.")
    marking.add_argument("uid")
    mode = marking.add_mutually_exclusive_group(required=True)
    mode.add_argument("--read", dest="read", action="store_true")
    mode.add_argument("--unread", dest="read", action="store_false")
    moving = sub.add_parser("move", parents=[common], help="Move a message to another folder.")
    moving.add_argument("uid")
    moving.add_argument("--to", dest="to_folder", required=True)
    deleting = sub.add_parser("delete", parents=[common], help="Move a message to Trash, or expunge it if it is already there.")
    deleting.add_argument("uid")
    attachment = sub.add_parser("attachment", parents=[common], help="Save an attachment.")
    attachment.add_argument("uid")
    attachment.add_argument("index", type=int)
    attachment.add_argument("--out")
    hosts = sub.add_parser("hosts", help="Show the IMAP and SMTP servers for an address. No login.")
    hosts.add_argument("address")
    serving = sub.add_parser("serve", help="Run the local JSON API used by the Quay desk.")
    serving.add_argument("--host", default="127.0.0.1")
    serving.add_argument("--port", type=int, default=8765)
    serving.add_argument("--allow-remote", action="store_true")
    # Silence unused lint for the shared folder argument object.
    del folder
    return parser


if __name__ == "__main__":
    raise SystemExit(main())

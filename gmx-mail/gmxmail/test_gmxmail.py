"""Unit tests that do not touch the network."""

from __future__ import annotations

import io
import json
import unittest
import email
from contextlib import redirect_stdout

from gmxmail.cli import main
from gmxmail.errors import GmxError
from gmxmail.http_api import dispatch
from gmxmail.parse import (
    build_search,
    decode_header_value,
    decode_mutf7,
    encode_mutf7,
    html_to_text,
    message_from_fetch,
    parse_list_line,
    servers_for,
    summaries_from_fetch,
)


class ParseTests(unittest.TestCase):
    def test_mutf7_roundtrip(self) -> None:
        for text in ("INBOX", "Entwürfe", "äöü & mehr", "Gesendete Elemente"):
            self.assertEqual(decode_mutf7(encode_mutf7(text)), text)
        self.assertEqual(encode_mutf7("Entwürfe"), "Entw&APw-rfe")

    def test_servers(self) -> None:
        self.assertEqual(servers_for("a@gmx.de")["imap_host"], "imap.gmx.net")
        self.assertEqual(servers_for("a@gmx.net")["smtp_host"], "mail.gmx.net")
        self.assertEqual(servers_for("a@gmx.com")["imap_host"], "imap.gmx.com")
        self.assertEqual(servers_for("a@gmx.co.uk")["imap_host"], "imap.gmx.com")
        self.assertEqual(servers_for("a@gmx.fr")["imap_host"], "imap.gmx.fr")
        self.assertEqual(servers_for("a@gmx.es")["smtp_host"], "mail.gmx.es")
        with self.assertRaises(GmxError):
            servers_for("a@gmail.com")

    def test_list_lines(self) -> None:
        inbox = parse_list_line(b'(\\HasNoChildren) "/" "INBOX"')
        assert inbox is not None
        self.assertEqual(inbox["name"], "INBOX")
        self.assertEqual(inbox["role"], "inbox")
        plain = parse_list_line(b'(\\HasNoChildren \\UnMarked) "/" INBOX')
        assert plain is not None
        self.assertEqual(plain["path"], "INBOX")
        drafts = parse_list_line(b'(\\HasNoChildren \\Drafts) "/" "Entw&APw-rfe"')
        assert drafts is not None
        self.assertEqual(drafts["name"], "Entwürfe")
        self.assertEqual(drafts["role"], "drafts")
        gmail = parse_list_line(b'(\\Noselect \\HasChildren) NIL "[Gmail]"')
        assert gmail is not None
        self.assertEqual(gmail["name"], "[Gmail]")
        self.assertIsNone(gmail["delimiter"])

    def test_headers_and_search(self) -> None:
        self.assertEqual(decode_header_value("=?utf-8?q?Hello_world?="), "Hello world")
        self.assertEqual(decode_header_value("=?utf-8?b?SGVsbG8=?="), "Hello")
        criteria = build_search('from:ada subject:proof unread catalog')
        self.assertIn(("FROM", "ada"), criteria)
        self.assertIn(("SUBJECT", "proof"), criteria)
        self.assertIn(("UNSEEN", None), criteria)
        self.assertIn(("TEXT", "catalog"), criteria)
        self.assertEqual(html_to_text("<p>Hello<br>there</p><script>alert(1)</script>"), "Hello\nthere")

    def test_fetch_summary_and_body(self) -> None:
        header = (
            b"From: Ada Lovelace <ada@example.com>\r\n"
            b"Subject: Analytical\r\n"
            b"Date: Tue, 20 Sep 2026 10:00:00 +0000\r\n"
        )
        meta = b"1 (UID 10 FLAGS (\\Seen) RFC822.SIZE 120 BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {80}"
        summaries = summaries_from_fetch([(meta, header), b")"], "INBOX")
        self.assertEqual(summaries[0]["uid"], "10")
        self.assertEqual(summaries[0]["subject"], "Analytical")
        self.assertTrue(summaries[0]["seen"])
        self.assertEqual(summaries[0]["from"]["email"], "ada@example.com")
        self.assertEqual(summaries[0]["media"], [])
        self.assertFalse(summaries[0]["has_attachments"])
        image = (
            b" BODYSTRUCTURE ("
            b'("TEXT" "PLAIN" ("CHARSET" "utf-8") NIL NIL "7BIT" 12 1 NIL NIL NIL NIL)'
            b'("IMAGE" "JPEG" ("NAME" "photo.jpg") NIL NIL "BASE64" 4000 NIL NIL '
            b'("ATTACHMENT" ("FILENAME" "photo.jpg")) NIL NIL)'
            b'("APPLICATION" "PKCS7-SIGNATURE" NIL NIL NIL "BASE64" 80 NIL NIL NIL NIL NIL)'
            b' "MIXED" ("BOUNDARY" "b") NIL NIL NIL))'
        )
        with_media = summaries_from_fetch([(meta, header), image], "INBOX")
        self.assertTrue(with_media[0]["has_attachments"])
        self.assertEqual(with_media[0]["media"][0]["content_type"], "image/jpeg")
        self.assertEqual(with_media[0]["media"][0]["filename"], "photo.jpg")
        self.assertEqual(len(with_media[0]["media"]), 1)
        plain = b' BODYSTRUCTURE ("TEXT" "PLAIN" ("CHARSET" "utf-8") NIL NIL "7BIT" 12 1 NIL NIL NIL NIL))'
        self.assertEqual(summaries_from_fetch([(meta, header), plain], "INBOX")[0]["media"], [])
        ahead = (
            b"1 (UID 11 FLAGS () RFC822.SIZE 9 BODYSTRUCTURE "
            b'(("TEXT" "HTML" NIL NIL NIL "7BIT" 4 1 NIL NIL NIL NIL)'
            b'("IMAGE" "PNG" NIL NIL NIL "BASE64" 20 NIL NIL ("INLINE" ("FILENAME" "logo.png")) NIL NIL)'
            b' "RELATED" NIL NIL NIL NIL) BODY[HEADER.FIELDS (FROM)] {4}'
        )
        inline = summaries_from_fetch([(ahead, b"From:\r\n\r\n")], "INBOX")
        self.assertEqual(inline[0]["media"][0]["content_type"], "image/png")
        raw = (
            b"From: Ada Lovelace <ada@example.com>\r\n"
            b"To: you@gmx.net\r\n"
            b"Subject: Analytical\r\n"
            b"Message-ID: <abc@example.com>\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Engine notes.\r\n"
        )
        full_meta = b"1 (UID 10 FLAGS () BODY[] {200}"
        message = message_from_fetch([(full_meta, raw)], "INBOX", "10")
        self.assertEqual(message["text"], "Engine notes.")
        self.assertEqual(message["message_id"], "<abc@example.com>")
        html = email.message_from_string(
            "From: a@b.c\r\nSubject: Hi\r\nContent-Type: text/html\r\n\r\n<p>Hello <b>there</b></p>\r\n",
            policy=email.policy.default,
        )
        from gmxmail.parse import body_and_attachments

        text, from_html, attachments = body_and_attachments(html)
        self.assertEqual(text, "Hello there")
        self.assertTrue(from_html)
        self.assertEqual(attachments, [])


class ApiTests(unittest.TestCase):
    def test_health_and_guardrails(self) -> None:
        status, payload = dispatch("GET", "/health", {}, b"")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        status, payload = dispatch("GET", "/v1/reference", {}, b"")
        self.assertIn("list_messages", payload["python"][2])
        status, payload = dispatch("GET", "/v1/folders", {}, b"")
        self.assertEqual(status, 401)
        status, payload = dispatch(
            "POST",
            "/v1/sessions",
            {},
            json.dumps({"email": "a@gmail.com", "password": "secret"}).encode(),
        )
        self.assertEqual(status, 400)
        self.assertNotIn("secret", payload["error"])
        status, payload = dispatch(
            "POST",
            "/v1/sessions",
            {},
            json.dumps({"email": "a@gmx.net", "password": ""}).encode(),
        )
        self.assertEqual(status, 400)
        status, payload = dispatch("POST", "/v1/sessions", {}, b"{")
        self.assertEqual(status, 400)

    def test_cli_help_and_hosts(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(main(["folders"]), 1)
        self.assertEqual(main(["send", "--to", "a@b.co", "--subject", "Hi"]), 1)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["hosts", "studio@gmx.at"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buffer.getvalue())["imap_host"], "imap.gmx.net")


if __name__ == "__main__":
    unittest.main()

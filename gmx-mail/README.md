# Quay

A GMX mailbox you can use from the command line, from Python, or from the desk in the browser. GMX has no public mail API. Quay uses IMAP and SMTP after you allow external access.

## Before the first login

1. Open GMX webmail on a computer, not the GMX phone app.
2. Open **E-Mail-Einstellungen** (your initials in the top bar, or the gear under the folder list).
3. Under **E-Mail empfangen**, open **POP3/IMAP**.
4. Turn on **POP3- und IMAP-Zugriff erlauben** and save. English mailboxes call this **Enable access to this account via POP3 and IMAP**.
5. Sign in with your full address. Use your normal password, or an application password if two-factor authentication is on. Create that under **Account verwalten → Login & Sicherheit → Anwendungsspezifische Passwörter**.

Quay chooses the servers from the address. `gmx.de`, `gmx.net`, `gmx.at`, and `gmx.ch` use `imap.gmx.net`. `gmx.com` uses `imap.gmx.com`.

## Install the command

On macOS or Linux, from this folder:

```bash
./install.sh
```

That puts `gmxmail` in `~/.local/bin`. If the shell cannot find it, add that directory to `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

The installer does not ask for your GMX password and does not start a server. Remove the command with `./install.sh --uninstall`.

## Run the command line

From this folder:

```bash
python3 -m gmxmail folders --email you@gmx.net
```

It asks for the password. To skip the prompt:

```bash
export GMX_EMAIL=you@gmx.net
export GMX_PASSWORD='the-password'
python3 -m gmxmail list
```

Prefer the environment variable. `--password` works, but the secret then shows up in the process list.

| Command | What it does |
| --- | --- |
| `folders` | List mailbox folders |
| `list` | Newest messages. A `*` means unread |
| `read UID` | Print one message. `--peek` leaves it unread |
| `search "from:ada subject:proof"` | Search the current folder |
| `attachment UID INDEX` | Save a file. The first file is index `0` |
| `send --to a@b.c --subject Hi --body "Hi"` | Send text. `--body-file` is still the message text, not an attachment |
| `mark UID --read` or `--unread` | Change the read flag |
| `move UID --to Archive` | Move a message |
| `delete UID` | Move it to Trash |
| `hosts you@gmx.net` | Show the servers. No login |

Add `--json` for JSON. Add `--folder "Sent"` to leave the inbox. `--limit` and `--page` walk the list. Each file saved with `attachment` must be 5 MB or smaller.

`list` prints one line per message:

```text
INBOX  2 message(s)
*    1842  2026-09-24 13:10  Ada Lovelace          Invoice  [image/jpeg, application/pdf]
     1841  2026-09-24 09:02  GMX                   Security notice
```

The bracket is empty when there is no file or picture. Types come from the message structure, so the list does not download the files. With `--json`, each message has `has_attachments` and `media`:

```json
"media": [{ "content_type": "image/jpeg", "filename": "photo.jpg" }]
```

Open it, then save a file:

```bash
python3 -m gmxmail read 1842 --peek
python3 -m gmxmail attachment 1842 0 --out photo.jpg
```

`read` prints the text and the attachment names. Pictures are not drawn in the terminal.

## Python

```python
from gmxmail import GmxClient

with GmxClient("you@gmx.net", "your-password") as gmx:
    page = gmx.list_messages("INBOX", limit=20)
    for message in page["messages"]:
        kinds = ", ".join(item["content_type"] for item in message["media"])
        print(message["uid"], message["subject"], kinds)
    note = gmx.get_message(page["messages"][0]["uid"], mark_seen=False)
    if note["attachments"]:
        saved = gmx.download_attachment(note["uid"], "INBOX", 0)
        open(saved["filename"], "wb").write(saved["data"])
```

The same object can search, send, reply, mark, move, and delete. Sending from Python is text only, same as the command line.

## Local HTTP API

Start the bridge (binds to localhost by default):

```bash
python3 -m gmxmail serve --host 127.0.0.1 --port 8765
```

Main routes:

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/health` | Liveness check |
| `POST` | `/v1/sessions` | Body: `{"email","password"}` → session token |
| `DELETE` | `/v1/sessions` | Bearer token required |
| `GET` | `/v1/folders` | Bearer token |
| `GET` | `/v1/messages` | Query: `folder`, `limit`, `page`, `unread` |
| `POST` | `/v1/send` | Body: `to`, `subject`, `body` |

Also available: `/v1/search`, `/v1/messages/{uid}`, attachments, flags, move, delete, reply, and `/v1/reference`.

## Note: self-sent mail

The **first** mail you send to your own GMX address may land in **Spam**. Mark it **Not Spam** once in GMX webmail; later self-sent messages should reach the inbox normally.

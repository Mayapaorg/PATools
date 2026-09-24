"""Quay's GMX mail library.

Talks to GMX over IMAP and SMTP. Consumer GMX has no public mail REST API;
external access has to be enabled under GMX settings → POP3 & IMAP.

    from gmxmail import GmxClient

    with GmxClient("you@gmx.net", "your-password") as gmx:
        for message in gmx.list_messages("INBOX", limit=10)["messages"]:
            print(message["subject"])
"""

from gmxmail.client import GmxClient, connect
from gmxmail.errors import GmxError
from gmxmail.parse import servers_for

__all__ = ["GmxClient", "GmxError", "connect", "servers_for"]
__version__ = "1.0.0"

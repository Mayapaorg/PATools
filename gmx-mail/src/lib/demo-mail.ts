import type { Folder, MailMessage } from "@/lib/mail-types";

export const DEMO_FOLDERS: Folder[] = [
  { name: "Inbox", path: "INBOX", role: "inbox" },
  { name: "Drafts", path: "Drafts", role: "drafts" },
  { name: "Sent", path: "Sent", role: "sent" },
  { name: "Archive", path: "Archive", role: "archive" },
  { name: "Spam", path: "Spam", role: "junk" },
  { name: "Trash", path: "Trash", role: "trash" },
];

const me = { name: "Lea Hart", email: "lea.hart@gmx.net" };

export const DEMO_MESSAGES: MailMessage[] = [
  {
    uid: "2401",
    folder: "INBOX",
    order: 60,
    from: { name: "Mara Klein", email: "mara.klein@example.com" },
    to: [me],
    cc: [],
    subject: "Keys for Thursday",
    date: "2026-09-24T09:14:00+03:00",
    dateLabel: "24 Sep, 09:14",
    seen: true,
    preview: "The studio key is in the blue tin above the meter. I'll be on the train until noon.",
    has_attachments: false,
    attachments: [],
    size: 1840,
    message_id: "<demo-2401@quay.invalid>",
    text: `Lea,

The studio key is in the blue tin above the meter. I'll be on the train until noon, so don't wait on me if the courier arrives early.

The autumn catalog proofs are with Nordlicht — they said the cover black is a little warm and want a second pass before Friday. If you agree, tell them to hold the inside pages.

I left the door code on the card in your desk drawer, not in this mail.

Mara`,
  },
  {
    uid: "2402",
    folder: "INBOX",
    order: 50,
    from: { name: "Nordlicht Books", email: "orders@nordlicht.example" },
    to: [me],
    cc: [],
    subject: "Your order is packed",
    date: "2026-09-23T18:40:00+03:00",
    dateLabel: "23 Sep, 18:40",
    seen: false,
    preview: "Two copies of Field Notes on Paper and one of the pressman's guide left the shop today.",
    has_attachments: false,
    attachments: [],
    size: 2104,
    message_id: "<demo-2402@quay.invalid>",
    text: `Hello Lea,

Two copies of Field Notes on Paper and one of the pressman's guide left the shop today. The parcel is marked for the studio door, not the flat.

If Thursday is awkward, reply with another day before noon and we will hold it.

Nordlicht Books`,
  },
  {
    uid: "2403",
    folder: "INBOX",
    order: 40,
    from: { name: "Hafen Studio", email: "press@hafen.example" },
    to: [me],
    cc: [{ name: "Mara Klein", email: "mara.klein@example.com" }],
    subject: "Proofs for the autumn catalog",
    date: "2026-09-22T11:05:00+03:00",
    dateLabel: "22 Sep, 11:05",
    seen: true,
    preview: "Cover black still reads warm under gallery light. Notes are in the attached sheet.",
    has_attachments: true,
    media: [{ content_type: "text/plain", filename: "catalog-notes.txt" }],
    attachments: [{ index: 0, filename: "catalog-notes.txt", content_type: "text/plain", size: 860 }],
    size: 48220,
    message_id: "<demo-2403@quay.invalid>",
    text: `Lea,

Cover black still reads warm under gallery light. I marked three spreads where the caption gray drops out.

Notes are in the attached sheet. We can print the inside pages while the cover is remade, if you sign off by Friday.

Hafen`,
  },
  {
    uid: "2404",
    folder: "INBOX",
    order: 30,
    from: { name: "Paper & Salt", email: "issue@paperandsalt.example" },
    to: [me],
    cc: [],
    subject: "September: ink, linen, and a late pear",
    date: "2026-09-20T08:00:00+03:00",
    dateLabel: "20 Sep, 08:00",
    seen: true,
    preview: "This month's letter is short. A linen mill in Galicia, and a recipe that wants a firm pear.",
    has_attachments: false,
    attachments: [],
    size: 6400,
    message_id: "<demo-2404@quay.invalid>",
    text: `This month's letter is short.

A linen mill outside A Coruña is still sizing cloth the slow way, and the piece on their dye book is the one to read if you only open one link. The kitchen note wants a firm pear, not a ripe one.

You're on the complimentary list for the studio. Reply unsubscribe and I'll take you off without a fuss.

— Paper & Salt`,
  },
  {
    uid: "2301",
    folder: "Sent",
    order: 20,
    from: me,
    to: [{ name: "Hafen Studio", email: "accounts@hafen.example" }],
    cc: [],
    subject: "Invoice 1842 is paid",
    date: "2026-09-18T16:22:00+03:00",
    dateLabel: "18 Sep, 16:22",
    seen: true,
    preview: "Paid this morning. Please send the receipt to the studio address.",
    has_attachments: false,
    attachments: [],
    size: 980,
    message_id: "<demo-2301@quay.invalid>",
    text: `Hello,

Invoice 1842 is paid. Please send the receipt to the studio address, not the flat.

Thank you,
Lea Hart`,
  },
  {
    uid: "2201",
    folder: "Drafts",
    order: 10,
    from: me,
    to: [{ name: "Mara Klein", email: "mara.klein@example.com" }],
    cc: [],
    subject: "Notes for the quay meeting",
    date: "2026-09-17T19:02:00+03:00",
    dateLabel: "17 Sep, 19:02",
    seen: true,
    preview: "Draft — agenda so far: cover reprint, courier window, who keeps the key tin.",
    has_attachments: false,
    attachments: [],
    size: 740,
    message_id: "<demo-2201@quay.invalid>",
    text: `Agenda so far:

- Cover reprint, yes or no before Friday
- Courier window on Thursday
- Who keeps the key tin next month

Still drafting. Don't send.`,
  },
  {
    uid: "2101",
    folder: "Spam",
    order: 5,
    from: { name: "List Desk", email: "lists@advertise.example" },
    to: [me],
    cc: [],
    subject: "Place your studio in our directory",
    date: "2026-09-12T04:12:00+03:00",
    dateLabel: "12 Sep, 04:12",
    seen: false,
    preview: "A paid listing is available for print studios. This is sample junk, not a real offer.",
    has_attachments: false,
    attachments: [],
    size: 1200,
    message_id: "<demo-2101@quay.invalid>",
    text: `A paid listing is available for print studios.

This message is sample junk inside the demo mailbox. It was not sent by a real directory, and nothing here should be answered.`,
  },
  {
    uid: "2001",
    folder: "Trash",
    order: 1,
    from: { name: "Hafen Studio", email: "press@hafen.example" },
    to: [me],
    cc: [],
    subject: "Superseded quote",
    date: "2026-09-02T13:30:00+03:00",
    dateLabel: "2 Sep, 13:30",
    seen: true,
    preview: "Ignore this figure. The revised quote went out the next morning.",
    has_attachments: false,
    attachments: [],
    size: 860,
    message_id: "<demo-2001@quay.invalid>",
    text: `Ignore this figure. The revised quote went out the next morning and is the one on the invoice.`,
  },
];

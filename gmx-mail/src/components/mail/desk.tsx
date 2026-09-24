import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  Archive,
  BookOpen,
  ChevronLeft,
  FilePen,
  Folder as FolderMark,
  Inbox,
  Menu,
  PenLine,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  Trash2,
} from "lucide-react";
import { DEMO_FOLDERS, DEMO_MESSAGES } from "@/lib/demo-mail";
import {
  bridgeHealth,
  changeRead,
  closeSession,
  fetchAttachment,
  loadMessages,
  moveMessage,
  openSession,
  readMessage,
  removeMessage,
  sendMessage,
} from "@/lib/mail.functions";
import type { Address, Attachment, Folder, MailMessage, MailSummary } from "@/lib/mail-types";
import { Guide } from "@/components/mail/guide";

type Draft = {
  to: string;
  cc: string;
  subject: string;
  body: string;
  inReplyTo: string;
  references: string;
};

const emptyDraft: Draft = { to: "", cc: "", subject: "", body: "", inReplyTo: "", references: "" };

const primaryBtn =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-on-primary disabled:opacity-50";
const quietBtn =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-line bg-card px-3 text-sm font-semibold text-ink disabled:opacity-50";
const sealBtn =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-seal px-3 text-sm font-semibold text-on-seal disabled:opacity-50";
const field =
  "min-h-11 w-full rounded-md border border-line bg-card px-3 text-ink outline-none placeholder:text-muted focus-visible:outline-2 focus-visible:outline-primary";

function cloneMessage(message: MailMessage): MailMessage {
  return {
    ...message,
    from: { ...message.from },
    to: message.to.map((item) => ({ ...item })),
    cc: message.cc.map((item) => ({ ...item })),
    attachments: message.attachments.map((item) => ({ ...item })),
  };
}

function person(address: Address): string {
  return address.name || address.email || "Unknown";
}

function formatWhen(iso: string | null | undefined, label?: string): string {
  if (label) return label;
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function mediaLabel(message: MailSummary): string {
  const types: string[] = [];
  for (const item of message.media ?? []) {
    if (item.content_type && !types.includes(item.content_type)) types.push(item.content_type);
  }
  return types.join(", ");
}

function matches(message: MailMessage, raw: string): boolean {
  const needle = raw.trim().toLowerCase();
  if (!needle) return true;
  if (needle === "unread" || needle === "is:unread") return !message.seen;
  const simplified = needle
    .replace(/\b(from|to|subject):/g, " ")
    .replace(/\bunread\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const hay = `${message.subject} ${message.from.name} ${message.from.email} ${message.text}`.toLowerCase();
  if (!simplified) return true;
  return simplified.split(" ").every((word) => hay.includes(word));
}

function quoteBody(message: MailMessage): string {
  const who = person(message.from);
  const when = formatWhen(message.date, message.dateLabel);
  const quoted = (message.text || "").split("\n").map((line) => `> ${line}`).join("\n");
  return `\n\nOn ${when || "an earlier date"}, ${who} wrote:\n\n${quoted}`;
}

function FolderGlyph({ role }: { role: string }) {
  const className = "size-4 shrink-0";
  if (role === "inbox") return <Inbox className={className} aria-hidden="true" />;
  if (role === "sent") return <Send className={className} aria-hidden="true" />;
  if (role === "drafts") return <FilePen className={className} aria-hidden="true" />;
  if (role === "trash") return <Trash2 className={className} aria-hidden="true" />;
  if (role === "junk") return <ShieldAlert className={className} aria-hidden="true" />;
  if (role === "archive") return <Archive className={className} aria-hidden="true" />;
  return <FolderMark className={className} aria-hidden="true" />;
}

function saveBlob(filename: string, type: string, data: BlobPart) {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function Desk() {
  const [mode, setMode] = useState<"sample" | "live">("sample");
  const [token, setToken] = useState<string | null>(null);
  const [account, setAccount] = useState<string | null>(null);
  const [hostLabel, setHostLabel] = useState<string | null>(null);
  const [folders, setFolders] = useState<Folder[]>(DEMO_FOLDERS);
  const [folderPath, setFolderPath] = useState("INBOX");
  const [mailbox, setMailbox] = useState<MailMessage[]>(() => DEMO_MESSAGES.map(cloneMessage));
  const [liveRows, setLiveRows] = useState<MailSummary[]>([]);
  const [liveTotal, setLiveTotal] = useState(0);
  const [livePage, setLivePage] = useState(1);
  const [opened, setOpened] = useState<MailMessage | null>(() => cloneMessage(DEMO_MESSAGES[0]));
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [section, setSection] = useState<"mail" | "guide">("mail");
  const [pane, setPane] = useState<"list" | "read" | "folders" | "guide">("list");
  const [bridge, setBridge] = useState<"checking" | "up" | "down">("checking");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [connectOpen, setConnectOpen] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [moveDest, setMoveDest] = useState("Archive");

  useEffect(() => {
    void bridgeHealth().then((result) => setBridge(result.ok ? "up" : "down"));
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setConnectOpen(false);
      setComposeOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const sampleRows = useMemo(
    () =>
      mailbox
        .filter((message) => message.folder === folderPath)
        .filter((message) => !unreadOnly || !message.seen)
        .filter((message) => matches(message, query))
        .sort((a, b) => (b.order ?? 0) - (a.order ?? 0)),
    [mailbox, folderPath, unreadOnly, query],
  );

  const rows: MailSummary[] = mode === "sample" ? sampleRows : liveRows;
  const folder = folders.find((item) => item.path === folderPath) ?? folders[0];
  const destinations = folders.filter((item) => item.path !== folderPath);
  const destValue = destinations.some((item) => item.path === moveDest) ? moveDest : (destinations[0]?.path ?? "");

  async function pull(session: string, nextFolder: string, page: number, search: string, unread: boolean) {
    const pageData = await loadMessages({
      data: { token: session, folder: nextFolder, page, query: search, unread },
    });
    setLiveRows(pageData.messages);
    setLiveTotal(pageData.total);
    setLivePage(pageData.page);
    setOpened(null);
  }

  async function run(task: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await task();
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Something went wrong.";
      if (/connect to gmx again|session expired/i.test(message)) disconnect(false);
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  function showGuide() {
    setSection("guide");
    setPane("guide");
  }

  function showMail() {
    setSection("mail");
    setPane("list");
  }

  function chooseFolder(next: Folder) {
    setFolderPath(next.path);
    setSection("mail");
    setPane("list");
    setQuery("");
    setAppliedQuery("");
    setUnreadOnly(false);
    if (mode === "sample") {
      const first = mailbox
        .filter((message) => message.folder === next.path)
        .sort((a, b) => (b.order ?? 0) - (a.order ?? 0))[0];
      setOpened(first ? cloneMessage(first) : null);
      return;
    }
    if (token) void run(() => pull(token, next.path, 1, "", false));
  }

  function openRow(summary: MailSummary) {
    setPane("read");
    if (mode === "sample") {
      const full = mailbox.find((message) => message.uid === summary.uid && message.folder === summary.folder);
      if (!full) return;
      setOpened(cloneMessage({ ...full, seen: true }));
      setMailbox((current) =>
        current.map((message) =>
          message.uid === summary.uid && message.folder === summary.folder ? { ...message, seen: true } : message,
        ),
      );
      return;
    }
    if (!token) return;
    void run(async () => {
      const full = await readMessage({ data: { token, folder: folderPath, uid: summary.uid } });
      setOpened(full);
      setLiveRows((current) => current.map((message) => (message.uid === summary.uid ? { ...message, seen: true } : message)));
    });
  }

  async function connect(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      const session = await openSession({ data: { email: email.trim(), password } });
      setPassword("");
      setToken(session.token);
      setAccount(session.email);
      const label = `${session.hosts.imap_host} · ${session.hosts.smtp_host}`;
      setHostLabel(label);
      setFolders(session.folders.length ? session.folders : DEMO_FOLDERS);
      setMode("live");
      setConnectOpen(false);
      sessionStorage.setItem("quay-token", session.token);
      sessionStorage.setItem("quay-email", session.email);
      sessionStorage.setItem("quay-hosts", label);
      const inbox = session.folders.find((item) => item.role === "inbox") ?? session.folders[0];
      const path = inbox?.path ?? "INBOX";
      setFolderPath(path);
      setSection("mail");
      setPane("list");
      setQuery("");
      setAppliedQuery("");
      await pull(session.token, path, 1, "", false);
      setNotice(`Connected to ${session.email}.`);
    });
  }

  function disconnect(tellBridge = true) {
    const current = token;
    setMode("sample");
    setToken(null);
    setAccount(null);
    setHostLabel(null);
    setFolders(DEMO_FOLDERS);
    setFolderPath("INBOX");
    setMailbox(DEMO_MESSAGES.map(cloneMessage));
    setOpened(cloneMessage(DEMO_MESSAGES[0]));
    setLiveRows([]);
    setQuery("");
    setAppliedQuery("");
    setUnreadOnly(false);
    setSection("mail");
    setPane("list");
    sessionStorage.removeItem("quay-token");
    sessionStorage.removeItem("quay-email");
    sessionStorage.removeItem("quay-hosts");
    if (tellBridge && current) void closeSession({ data: { token: current } });
  }

  function resetSample() {
    setMailbox(DEMO_MESSAGES.map(cloneMessage));
    setOpened(cloneMessage(DEMO_MESSAGES[0]));
    setFolderPath("INBOX");
    setQuery("");
    setNotice("Sample mailbox restored.");
  }

  async function refresh() {
    if (mode !== "live" || !token) return;
    await run(() => pull(token, folderPath, livePage, appliedQuery, unreadOnly));
  }

  function onSearch(event: FormEvent) {
    event.preventDefault();
    setAppliedQuery(query);
    if (mode === "live" && token) void run(() => pull(token, folderPath, 1, query, unreadOnly));
  }

  function toggleUnread() {
    const next = !unreadOnly;
    setUnreadOnly(next);
    if (mode === "live" && token) void run(() => pull(token, folderPath, 1, appliedQuery, next));
  }

  async function onSend(event: FormEvent) {
    event.preventDefault();
    if (!draft.to.trim() || !draft.subject.trim()) {
      setError("Add a recipient and a subject.");
      return;
    }
    if (mode === "sample") {
      const sent: MailMessage = {
        uid: `s${Date.now()}`,
        folder: "Sent",
        order: Date.now(),
        from: { name: "Lea Hart", email: "lea.hart@gmx.net" },
        to: draft.to.split(/[,;]/).map((item) => ({ name: "", email: item.trim() })).filter((item) => item.email),
        cc: [],
        subject: draft.subject.trim(),
        date: null,
        dateLabel: "Just now",
        seen: true,
        preview: draft.body.trim().slice(0, 180),
        text: draft.body,
        attachments: [],
        has_attachments: false,
      };
      setMailbox((current) => [sent, ...current]);
      setComposeOpen(false);
      setDraft(emptyDraft);
      setNotice("Saved in the sample Sent folder. Nothing was delivered.");
      return;
    }
    if (!token) return;
    await run(async () => {
      const result = await sendMessage({
        data: {
          token,
          to: draft.to,
          cc: draft.cc,
          subject: draft.subject,
          body: draft.body,
          inReplyTo: draft.inReplyTo,
          references: draft.references,
        },
      });
      setComposeOpen(false);
      setDraft(emptyDraft);
      setNotice(result.saved_to_sent ? "Sent, and a copy was saved in Sent." : "Sent.");
      await pull(token, folderPath, 1, appliedQuery, unreadOnly);
    });
  }

  function startReply() {
    if (!opened) return;
    const subject = opened.subject.toLowerCase().startsWith("re:") ? opened.subject : `Re: ${opened.subject}`;
    setDraft({
      to: opened.from.email,
      cc: "",
      subject,
      body: quoteBody(opened),
      inReplyTo: opened.message_id || "",
      references: opened.message_id || "",
    });
    setComposeOpen(true);
  }

  async function mark(read: boolean) {
    if (!opened) return;
    if (mode === "sample") {
      setMailbox((current) =>
        current.map((message) =>
          message.uid === opened.uid && message.folder === opened.folder ? { ...message, seen: read } : message,
        ),
      );
      setOpened({ ...opened, seen: read });
      return;
    }
    if (!token) return;
    await run(async () => {
      await changeRead({ data: { token, folder: opened.folder || folderPath, uid: opened.uid, read } });
      setOpened({ ...opened, seen: read });
      setLiveRows((current) => current.map((message) => (message.uid === opened.uid ? { ...message, seen: read } : message)));
    });
  }

  async function remove() {
    if (!opened) return;
    if (mode === "sample") {
      setMailbox((current) => {
        if (opened.folder === "Trash") {
          return current.filter((message) => !(message.uid === opened.uid && message.folder === opened.folder));
        }
        return current.map((message) =>
          message.uid === opened.uid && message.folder === opened.folder ? { ...message, folder: "Trash", seen: true } : message,
        );
      });
      setOpened(null);
      setPane("list");
      setNotice(opened.folder === "Trash" ? "Deleted from the sample Trash." : "Moved to the sample Trash.");
      return;
    }
    if (!token) return;
    const uid = opened.uid;
    await run(async () => {
      await removeMessage({ data: { token, folder: folderPath, uid } });
      setOpened(null);
      setPane("list");
      setNotice("Moved to Trash, or deleted if it was already there.");
      await pull(token, folderPath, livePage, appliedQuery, unreadOnly);
    });
  }

  async function move() {
    if (!opened || !destValue) return;
    if (mode === "sample") {
      setMailbox((current) =>
        current.map((message) =>
          message.uid === opened.uid && message.folder === opened.folder ? { ...message, folder: destValue } : message,
        ),
      );
      setOpened(null);
      setPane("list");
      setNotice("Moved inside the sample mailbox.");
      return;
    }
    if (!token) return;
    const uid = opened.uid;
    await run(async () => {
      await moveMessage({ data: { token, folder: folderPath, uid, dest: destValue } });
      setOpened(null);
      setPane("list");
      setNotice("Moved.");
      await pull(token, folderPath, livePage, appliedQuery, unreadOnly);
    });
  }

  async function download(attachment: Attachment) {
    if (mode === "sample") {
      saveBlob(
        attachment.filename,
        "text/plain",
        `Sample attachment from the demo mailbox.\n${attachment.filename}\n`,
      );
      return;
    }
    if (!token || !opened) return;
    await run(async () => {
      const file = await fetchAttachment({
        data: { token, folder: folderPath, uid: opened.uid, index: attachment.index },
      });
      const binary = atob(file.data_base64);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      saveBlob(file.filename, file.content_type, bytes);
    });
  }

  const unreadIn = (path: string) =>
    mode === "sample" ? mailbox.filter((message) => message.folder === path && !message.seen).length : 0;

  const showingGuide = section === "guide";
  const listClass = showingGuide ? "hidden" : `${pane === "list" ? "flex" : "hidden"} min-h-0 flex-col lg:flex`;
  const readClass = showingGuide ? "hidden" : `${pane === "read" ? "flex" : "hidden"} min-h-0 flex-col lg:flex`;
  const folderClass = `${pane === "folders" ? "flex" : "hidden"} min-h-0 flex-col border-line lg:flex lg:border-r`;

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-paper text-ink">
      <header className="flex shrink-0 flex-col gap-3 px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={`${quietBtn} px-3 lg:hidden`} onClick={() => setPane("folders")} aria-label="Folders">
            <Menu className="size-4" aria-hidden="true" />
          </button>
          <div className="flex items-center gap-3">
            <span className="grid size-11 place-items-center rounded-md bg-primary font-display text-xl text-on-primary">Q</span>
            <div>
              <h1 className="text-2xl leading-none text-ink">Quay</h1>
              <p className="text-sm text-muted">
                {mode === "live" ? account : "Sample mailbox"}
                {" · "}
                {bridge === "up" ? "Bridge ready" : bridge === "down" ? "Bridge offline" : "Checking bridge"}
              </p>
            </div>
          </div>
          <div className="ml-auto flex flex-wrap gap-2">
            <button type="button" className={quietBtn} onClick={() => setComposeOpen(true)}>
              <PenLine className="size-4" aria-hidden="true" />
              Compose
            </button>
            {mode === "live" ? (
              <button type="button" className={quietBtn} onClick={() => disconnect(true)}>
                Disconnect
              </button>
            ) : (
              <button type="button" className={primaryBtn} onClick={() => setConnectOpen(true)}>
                Connect GMX
              </button>
            )}
          </div>
        </div>
        <form className="flex min-w-0 gap-2" onSubmit={onSearch}>
          <label className="sr-only" htmlFor="mail-search">
            Search mail
          </label>
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" aria-hidden="true" />
            <input
              id="mail-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search words, from:, subject:, unread"
              className={`${field} pl-9`}
            />
          </div>
          <button type="submit" className={quietBtn}>
            Search
          </button>
        </form>
      </header>
      <div className="h-0.5 shrink-0 bg-seal" />
      {error ? (
        <p role="alert" className="shrink-0 border-b border-line bg-card px-4 py-2 text-sm text-seal">
          {error}
        </p>
      ) : null}
      {notice ? <p className="shrink-0 border-b border-line bg-card px-4 py-2 text-sm text-primary">{notice}</p> : null}

      <div
        className={`grid min-h-0 flex-1 ${showingGuide ? "lg:grid-cols-[14rem_minmax(0,1fr)]" : "lg:grid-cols-[14rem_minmax(0,22rem)_minmax(0,1fr)]"}`}
      >
        <nav className={folderClass} aria-label="Folders">
          <div className="flex items-center justify-between px-3 py-3 lg:hidden">
            <p className="font-display text-xl">Folders</p>
            <button type="button" className={quietBtn} onClick={() => setPane("list")}>
              Close
            </button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-2 pb-6">
            {folders.map((item) => {
              const active = section === "mail" && item.path === folderPath;
              const count = unreadIn(item.path);
              return (
                <button
                  key={item.path}
                  type="button"
                  onClick={() => chooseFolder(item)}
                  className={`flex min-h-11 items-center gap-2 rounded-md px-3 text-left text-sm font-semibold ${active ? "bg-primary text-on-primary" : "text-ink hover:bg-card"}`}
                >
                  <FolderGlyph role={item.role} />
                  <span className="min-w-0 flex-1 truncate">{item.name}</span>
                  {count > 0 ? (
                    <span className="rounded-md bg-seal px-2 text-xs font-semibold text-on-seal tabular-nums">{count}</span>
                  ) : null}
                </button>
              );
            })}
            <button
              type="button"
              onClick={showGuide}
              className={`mt-2 flex min-h-11 items-center gap-2 rounded-md px-3 text-left text-sm font-semibold ${showingGuide ? "bg-primary text-on-primary" : "text-ink hover:bg-card"}`}
            >
              <BookOpen className="size-4 shrink-0" aria-hidden="true" />
              Library & CLI
            </button>
            {mode === "sample" ? (
              <button type="button" onClick={resetSample} className="mt-1 min-h-11 px-3 text-left text-sm font-semibold text-muted">
                Reset sample
              </button>
            ) : null}
          </div>
        </nav>

        {showingGuide ? <Guide onBack={showMail} /> : null}

        <section className={listClass} aria-label="Messages">
          <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
            <div className="min-w-0">
              <h2 className="truncate text-xl text-ink">{folder?.name ?? "Mail"}</h2>
              <p className="text-sm text-muted">
                {mode === "sample"
                  ? `${rows.length} in view · not your account`
                  : `${liveTotal} in folder${hostLabel ? ` · ${hostLabel}` : ""}`}
              </p>
            </div>
            <div className="flex shrink-0 gap-2">
              <button type="button" className={unreadOnly ? primaryBtn : quietBtn} onClick={toggleUnread}>
                Unread
              </button>
              {mode === "live" ? (
                <button type="button" className={quietBtn} onClick={() => void refresh()} disabled={busy} aria-label="Refresh">
                  <RefreshCw className={`size-4 ${busy ? "motion-safe:animate-spin" : ""}`} aria-hidden="true" />
                </button>
              ) : null}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {rows.length === 0 ? (
              <p className="px-4 py-8 text-muted">Nothing in this folder{query ? " matches that search" : ""}.</p>
            ) : (
              rows.map((message) => {
                const selected = opened?.uid === message.uid && (opened.folder === message.folder || mode === "live");
                return (
                  <button
                    key={`${message.folder}-${message.uid}`}
                    type="button"
                    onClick={() => openRow(message)}
                    aria-current={selected ? "true" : undefined}
                    className={`flex w-full min-w-0 flex-col gap-1 border-b border-line px-4 py-3 text-left ${selected ? "bg-primary/10" : "hover:bg-card"}`}
                  >
                    <span className="flex items-baseline gap-2">
                      {!message.seen ? <span className="size-2 shrink-0 rounded-full bg-seal" aria-label="Unread" /> : null}
                      <span className={`min-w-0 flex-1 truncate ${message.seen ? "font-medium" : "font-semibold"}`}>
                        {person(message.from)}
                      </span>
                      <span className="shrink-0 text-sm text-muted tabular-nums">{formatWhen(message.date, message.dateLabel)}</span>
                    </span>
                    <span className={`truncate ${message.seen ? "" : "font-semibold"}`}>{message.subject}</span>
                    {mediaLabel(message) ? <span className="truncate text-sm text-muted">{mediaLabel(message)}</span> : null}
                    {message.preview ? <span className="truncate text-sm text-muted">{message.preview}</span> : null}
                  </button>
                );
              })
            )}
            {mode === "live" && (livePage > 1 || livePage * 30 < liveTotal) ? (
              <div className="flex gap-2 p-4">
                {livePage > 1 ? (
                  <button
                    type="button"
                    className={quietBtn}
                    disabled={busy}
                    onClick={() => token && void run(() => pull(token, folderPath, livePage - 1, appliedQuery, unreadOnly))}
                  >
                    Newer page
                  </button>
                ) : null}
                {livePage * 30 < liveTotal ? (
                  <button
                    type="button"
                    className={quietBtn}
                    disabled={busy}
                    onClick={() => token && void run(() => pull(token, folderPath, livePage + 1, appliedQuery, unreadOnly))}
                  >
                    Older page
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        </section>

        <article className={`${readClass} border-line lg:border-l`} aria-label="Reading pane">
          {opened ? (
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6">
              <button type="button" className={`${quietBtn} mb-3 lg:hidden`} onClick={() => setPane("list")}>
                <ChevronLeft className="size-4" aria-hidden="true" />
                Back
              </button>
              <h2 className="text-2xl text-ink">{opened.subject}</h2>
              <p className="mt-3 text-sm text-muted">{formatWhen(opened.date, opened.dateLabel)}</p>
              <p className="mt-4">
                <span className="font-semibold">{person(opened.from)}</span>
                {opened.from.email ? <span className="text-muted"> {opened.from.email}</span> : null}
              </p>
              {opened.to.length ? (
                <p className="text-sm text-muted">To {opened.to.map((item) => person(item) || item.email).join(", ")}</p>
              ) : null}
              {opened.cc.length ? (
                <p className="text-sm text-muted">Cc {opened.cc.map((item) => item.email || person(item)).join(", ")}</p>
              ) : null}
              <div className="mt-4 flex flex-wrap gap-2">
                <button type="button" className={primaryBtn} onClick={startReply} disabled={!opened.from.email}>
                  Reply
                </button>
                <button type="button" className={quietBtn} onClick={() => void mark(!opened.seen)} disabled={busy}>
                  {opened.seen ? "Mark unread" : "Mark read"}
                </button>
                <button type="button" className={sealBtn} onClick={() => void remove()} disabled={busy}>
                  Delete
                </button>
                <label className="sr-only" htmlFor="move-dest">
                  Move to
                </label>
                <select
                  id="move-dest"
                  className={field + " w-auto"}
                  value={destValue}
                  onChange={(event) => setMoveDest(event.target.value)}
                >
                  {destinations.map((item) => (
                    <option key={item.path} value={item.path}>
                      {item.name}
                    </option>
                  ))}
                </select>
                <button type="button" className={quietBtn} onClick={() => void move()} disabled={busy || !destValue}>
                  Move
                </button>
              </div>
              {opened.attachments?.length ? (
                <ul className="mt-4 flex flex-col gap-2">
                  {opened.attachments.map((attachment) => (
                    <li key={attachment.index}>
                      <button type="button" className={quietBtn} onClick={() => void download(attachment)}>
                        {attachment.filename}
                        <span className="font-medium text-muted">{formatSize(attachment.size)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {opened.text_from_html ? <p className="mt-4 text-sm text-muted">Shown as plain text. The original was HTML.</p> : null}
              <p className="mt-5 pb-16 text-pretty whitespace-pre-wrap text-ink">{opened.text || "This message has no text body."}</p>
            </div>
          ) : (
            <div className="flex flex-1 flex-col justify-center px-6 py-10">
              <button type="button" className={`${quietBtn} mb-4 self-start lg:hidden`} onClick={() => setPane("list")}>
                <ChevronLeft className="size-4" aria-hidden="true" />
                Back
              </button>
              <h2 className="text-2xl text-ink">Choose a message</h2>
              <p className="mt-2 max-w-sm text-muted">
                {mode === "live"
                  ? "Open something from the list. Delete moves it to Trash."
                  : "This is sample mail so you can learn the desk. Connect GMX when you want your own postfach."}
              </p>
            </div>
          )}
        </article>
      </div>

      {connectOpen ? (
        <div className="fixed inset-0 z-20 flex items-end justify-center bg-ink/40 p-4 sm:items-center">
          <form
            role="dialog"
            aria-modal="true"
            aria-labelledby="connect-title"
            onSubmit={(event) => void connect(event)}
            className="w-full max-w-md rounded-lg border border-line bg-card p-5"
          >
            <h2 id="connect-title" className="text-2xl text-ink">
              Connect GMX
            </h2>
            <p className="mt-2 text-sm text-pretty text-muted">
              In GMX webmail, open Settings, then POP3 & IMAP, and allow external programs. The password stays in the
              mail bridge for this session only. It is not saved in the desk.
            </p>
            <label className="mt-4 block text-sm font-semibold" htmlFor="gmx-email">
              Email
            </label>
            <input
              id="gmx-email"
              className={`${field} mt-1`}
              autoComplete="username"
              inputMode="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@gmx.net"
              autoFocus
            />
            <label className="mt-3 block text-sm font-semibold" htmlFor="gmx-password">
              Password
            </label>
            <input
              id="gmx-password"
              className={`${field} mt-1`}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="submit" className={primaryBtn} disabled={busy}>
                {busy ? "Connecting…" : "Connect"}
              </button>
              <button type="button" className={quietBtn} onClick={() => setConnectOpen(false)}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {composeOpen ? (
        <div className="fixed inset-0 z-20 flex items-end justify-center bg-ink/40 p-4 sm:items-center">
          <form
            role="dialog"
            aria-modal="true"
            aria-labelledby="compose-title"
            onSubmit={(event) => void onSend(event)}
            className="max-h-[90dvh] w-full max-w-xl overflow-y-auto rounded-lg border border-line bg-card p-5"
          >
            <h2 id="compose-title" className="text-2xl text-ink">
              {draft.inReplyTo ? "Reply" : "New message"}
            </h2>
            <label className="mt-4 block text-sm font-semibold" htmlFor="compose-to">
              To
            </label>
            <input id="compose-to" className={`${field} mt-1`} value={draft.to} onChange={(event) => setDraft({ ...draft, to: event.target.value })} />
            <label className="mt-3 block text-sm font-semibold" htmlFor="compose-cc">
              Cc
            </label>
            <input id="compose-cc" className={`${field} mt-1`} value={draft.cc} onChange={(event) => setDraft({ ...draft, cc: event.target.value })} />
            <label className="mt-3 block text-sm font-semibold" htmlFor="compose-subject">
              Subject
            </label>
            <input
              id="compose-subject"
              className={`${field} mt-1`}
              value={draft.subject}
              onChange={(event) => setDraft({ ...draft, subject: event.target.value })}
            />
            <label className="mt-3 block text-sm font-semibold" htmlFor="compose-body">
              Message
            </label>
            <textarea
              id="compose-body"
              className={`${field} mt-1 min-h-40 py-2`}
              value={draft.body}
              onChange={(event) => setDraft({ ...draft, body: event.target.value })}
            />
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="submit" className={primaryBtn} disabled={busy}>
                {mode === "sample" ? "File in sample Sent" : "Send"}
              </button>
              <button type="button" className={quietBtn} onClick={() => setComposeOpen(false)}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

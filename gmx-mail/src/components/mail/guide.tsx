export function Guide({ onBack }: { onBack: () => void }) {
  return (
    <article className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-8">
      <button type="button" onClick={onBack} className="mb-4 min-h-11 text-sm font-semibold text-primary lg:hidden">
        Back to mail
      </button>
      <p className="text-sm font-semibold tracking-wide text-seal uppercase">Library</p>
      <h2 className="mt-1 text-3xl text-ink">The same mailbox, three ways</h2>
      <p className="mt-3 max-w-2xl text-pretty text-muted">
        Quay is a Python mailbox library. The desk in front of you calls it. The command line calls it. GMX has no
        public mail REST API, so both speak IMAP on port 993 and SMTP on port 465.
      </p>

      <section className="mt-8 max-w-2xl">
        <h3 className="text-xl text-ink">Before a real login</h3>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-ink">
          <li>In GMX webmail, open Settings, then POP3 & IMAP.</li>
          <li>Turn on access for external programs. It is off until you do.</li>
          <li>Sign in with the full address. Use the account password, or an application password if GMX asks for one.</li>
        </ol>
        <p className="mt-3 text-sm text-muted">
          Addresses ending in gmx.de, gmx.net, gmx.at, and gmx.ch use imap.gmx.net. gmx.com uses imap.gmx.com. French
          and Spanish accounts use their own hosts. The library picks this for you.
        </p>
      </section>

      <section className="mt-8 max-w-2xl">
        <h3 className="text-xl text-ink">Python API</h3>
        <pre className="mt-3 overflow-x-auto rounded-lg border border-line bg-card p-4 text-sm leading-relaxed text-ink">{`from gmxmail import GmxClient

with GmxClient("you@gmx.net", "your-password") as gmx:
    page = gmx.list_messages("INBOX", limit=10)
    print(page["messages"][0]["subject"])
    note = gmx.get_message(page["messages"][0]["uid"])
    gmx.send(
        to="friend@example.com",
        subject="Hello",
        body="Sent from Quay.",
    )
    gmx.delete(note["uid"], "INBOX")`}</pre>
        <ul className="mt-4 space-y-2 text-sm text-ink">
          <li><span className="font-semibold">list_folders</span> — names, paths, and roles such as inbox, sent, trash.</li>
          <li><span className="font-semibold">list_messages</span> — newest first. Each row includes media types such as image/jpeg when the message has a file or picture.</li>
          <li><span className="font-semibold">get_message</span> — full text. HTML is converted to plain text.</li>
          <li><span className="font-semibold">search</span> — from:, to:, subject:, unread, plus free text.</li>
          <li><span className="font-semibold">send / reply</span> — SMTP, then a copy in Sent when GMX allows it.</li>
          <li><span className="font-semibold">set_read, move, delete</span> — delete moves to Trash, then expunges.</li>
          <li><span className="font-semibold">download_attachment</span> — by numeric index on the message.</li>
        </ul>
      </section>

      <section className="mt-8 max-w-2xl">
        <h3 className="text-xl text-ink">Command line</h3>
        <p className="mt-2 text-sm text-muted">
          Set GMX_EMAIL and GMX_PASSWORD. The password flag exists, but the environment keeps it out of the process list.
          Add --json if another program will read the output.
        </p>
        <pre className="mt-3 overflow-x-auto rounded-lg border border-line bg-card p-4 text-sm leading-relaxed text-ink">{`./install.sh
gmxmail folders
gmxmail list --folder INBOX --limit 20 --unread
gmxmail read 2401 --peek
gmxmail attachment 2401 0 --out photo.jpg
gmxmail search "from:mara subject:keys"
gmxmail send --to friend@example.com --subject Hello --body "Hi"
gmxmail mark 2401 --unread
gmxmail move 2401 --to Archive
gmxmail delete 2401
gmxmail hosts you@gmx.net`}</pre>
      </section>

      <section className="mt-8 mb-16 max-w-2xl">
        <h3 className="text-xl text-ink">What the desk is doing</h3>
        <p className="mt-2 text-pretty text-ink">
          Connect stores the password only in the mail bridge process, returns a session token, and forgets it when you
          disconnect or after 45 minutes of quiet. The sample mailbox never leaves this page. Switching to your GMX
          account replaces it until you disconnect.
        </p>
      </section>
    </article>
  );
}

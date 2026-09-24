import { createServerFn } from "@tanstack/react-start";
import type { Folder, MailMessage, MailPage, SessionInfo } from "@/lib/mail-types";

async function bridge() {
  return import("./gmx-bridge.server.ts");
}

function asRecord(data: unknown): Record<string, unknown> {
  if (!data || typeof data !== "object") throw new Error("That request was empty.");
  return data as Record<string, unknown>;
}

function emailOf(value: unknown): string {
  const email = typeof value === "string" ? value.trim() : "";
  const domain = email.split("@")[1]?.toLowerCase() ?? "";
  if (!/^[^@\s]+@[^@\s]+$/.test(email) || !domain.split(".").includes("gmx")) {
    throw new Error("Use a GMX address such as name@gmx.com or name@gmx.net.");
  }
  return email;
}

function tokenOf(value: unknown): string {
  const token = typeof value === "string" ? value : "";
  if (!/^[A-Za-z0-9_-]{20,}$/.test(token)) throw new Error("Connect to GMX again.");
  return token;
}

function folderOf(value: unknown, fallback = "INBOX"): string {
  const folder = typeof value === "string" && value.trim() ? value.trim() : fallback;
  if (!folder || folder.length > 400 || /[\r\n\u0000]/.test(folder)) {
    throw new Error("That folder name cannot be used.");
  }
  return folder;
}

function uidOf(value: unknown): string {
  const uid = typeof value === "string" ? value : "";
  if (!/^\d{1,20}$/.test(uid)) throw new Error("That message id is not valid.");
  return uid;
}

export const bridgeHealth = createServerFn({ method: "GET" }).handler(async () => {
  const { gmxRequest } = await bridge();
  try {
    await gmxRequest("/health");
    return { ok: true as const };
  } catch {
    return { ok: false as const };
  }
});

export const openSession = createServerFn({ method: "POST" })
  .validator((data: { email: string; password: string }) => {
    const record = asRecord(data);
    const email = emailOf(record.email);
    const password = typeof record.password === "string" ? record.password : "";
    if (!password) throw new Error("Password is required.");
    if (/[\r\n\0]/.test(password)) throw new Error("That password cannot be sent.");
    return { email, password };
  })
  .handler(async ({ data }): Promise<SessionInfo> => {
    const { gmxRequest } = await bridge();
    return gmxRequest<SessionInfo>("/v1/sessions", { method: "POST", body: data });
  });

export const closeSession = createServerFn({ method: "POST" })
  .validator((data: { token: string }) => ({ token: tokenOf(asRecord(data).token) }))
  .handler(async ({ data }) => {
    const { gmxRequest } = await bridge();
    try {
      await gmxRequest("/v1/sessions", { method: "DELETE", token: data.token });
    } catch {
      return { ok: false as const };
    }
    return { ok: true as const };
  });

export const loadFolders = createServerFn({ method: "POST" })
  .validator((data: { token: string }) => ({ token: tokenOf(asRecord(data).token) }))
  .handler(async ({ data }) => {
    const { gmxRequest } = await bridge();
    return gmxRequest<{ folders: Folder[] }>("/v1/folders", { token: data.token });
  });

export const loadMessages = createServerFn({ method: "POST" })
  .validator((data: { token: string; folder: string; page?: number; query?: string; unread?: boolean }) => {
    const record = asRecord(data);
    const page = Number(record.page ?? 1);
    return {
      token: tokenOf(record.token),
      folder: folderOf(record.folder),
      page: Number.isFinite(page) ? Math.max(1, Math.min(1000, Math.trunc(page))) : 1,
      query: typeof record.query === "string" ? record.query.slice(0, 500) : "",
      unread: Boolean(record.unread),
    };
  })
  .handler(async ({ data }): Promise<MailPage> => {
    const { gmxRequest } = await bridge();
    const params = new URLSearchParams();
    params.set("folder", data.folder);
    params.set("limit", "30");
    if (data.query.trim()) {
      params.set("q", data.query.trim());
      return gmxRequest<MailPage>(`/v1/search?${params}`, { token: data.token });
    }
    params.set("page", String(data.page));
    if (data.unread) params.set("unread", "1");
    return gmxRequest<MailPage>(`/v1/messages?${params}`, { token: data.token });
  });

export const readMessage = createServerFn({ method: "POST" })
  .validator((data: { token: string; folder: string; uid: string }) => {
    const record = asRecord(data);
    return { token: tokenOf(record.token), folder: folderOf(record.folder), uid: uidOf(record.uid) };
  })
  .handler(async ({ data }): Promise<MailMessage> => {
    const { gmxRequest } = await bridge();
    const params = new URLSearchParams({ folder: data.folder });
    return gmxRequest<MailMessage>(`/v1/messages/${data.uid}?${params}`, { token: data.token });
  });

export const changeRead = createServerFn({ method: "POST" })
  .validator((data: { token: string; folder: string; uid: string; read: boolean }) => {
    const record = asRecord(data);
    return {
      token: tokenOf(record.token),
      folder: folderOf(record.folder),
      uid: uidOf(record.uid),
      read: Boolean(record.read),
    };
  })
  .handler(async ({ data }): Promise<{ uid: string; folder: string; seen: boolean }> => {
    const { gmxRequest } = await bridge();
    return gmxRequest<{ uid: string; folder: string; seen: boolean }>(`/v1/messages/${data.uid}/flags`, {
      method: "POST",
      token: data.token,
      body: { folder: data.folder, read: data.read },
    });
  });

export const removeMessage = createServerFn({ method: "POST" })
  .validator((data: { token: string; folder: string; uid: string }) => {
    const record = asRecord(data);
    return { token: tokenOf(record.token), folder: folderOf(record.folder), uid: uidOf(record.uid) };
  })
  .handler(async ({ data }): Promise<{ uid: string; folder: string; trashed: boolean }> => {
    const { gmxRequest } = await bridge();
    return gmxRequest<{ uid: string; folder: string; trashed: boolean }>(`/v1/messages/${data.uid}/delete`, {
      method: "POST",
      token: data.token,
      body: { folder: data.folder },
    });
  });

export const moveMessage = createServerFn({ method: "POST" })
  .validator((data: { token: string; folder: string; uid: string; dest: string }) => {
    const record = asRecord(data);
    return {
      token: tokenOf(record.token),
      folder: folderOf(record.folder),
      uid: uidOf(record.uid),
      dest: folderOf(record.dest, ""),
    };
  })
  .handler(async ({ data }): Promise<{ uid: string; dest: string }> => {
    const { gmxRequest } = await bridge();
    return gmxRequest<{ uid: string; dest: string }>(`/v1/messages/${data.uid}/move`, {
      method: "POST",
      token: data.token,
      body: { folder: data.folder, dest: data.dest },
    });
  });

export const sendMessage = createServerFn({ method: "POST" })
  .validator(
    (data: {
      token: string;
      to: string;
      cc?: string;
      subject: string;
      body: string;
      inReplyTo?: string;
      references?: string;
    }) => {
      const record = asRecord(data);
      const subject = typeof record.subject === "string" ? record.subject.trim() : "";
      const body = typeof record.body === "string" ? record.body : "";
      const to = typeof record.to === "string" ? record.to.trim() : "";
      if (!to) throw new Error("Add at least one recipient.");
      if (!subject) throw new Error("Subject is required.");
      if (body.length > 1_000_000) throw new Error("That message is too long.");
      return {
        token: tokenOf(record.token),
        to,
        cc: typeof record.cc === "string" ? record.cc.trim() : "",
        subject,
        body,
        inReplyTo: typeof record.inReplyTo === "string" ? record.inReplyTo : "",
        references: typeof record.references === "string" ? record.references : "",
      };
    },
  )
  .handler(async ({ data }) => {
    const { gmxRequest } = await bridge();
    return gmxRequest<{ sent: boolean; saved_to_sent: boolean }>("/v1/send", {
      method: "POST",
      token: data.token,
      body: {
        to: data.to,
        cc: data.cc,
        subject: data.subject,
        body: data.body,
        in_reply_to: data.inReplyTo || null,
        references: data.references || null,
      },
    });
  });

export const fetchAttachment = createServerFn({ method: "POST" })
  .validator((data: { token: string; folder: string; uid: string; index: number }) => {
    const record = asRecord(data);
    const index = Number(record.index);
    if (!Number.isInteger(index) || index < 0 || index > 50) throw new Error("That attachment is not available.");
    return {
      token: tokenOf(record.token),
      folder: folderOf(record.folder),
      uid: uidOf(record.uid),
      index,
    };
  })
  .handler(async ({ data }) => {
    const { gmxRequest } = await bridge();
    const params = new URLSearchParams({ folder: data.folder });
    return gmxRequest<{ filename: string; content_type: string; data_base64: string }>(
      `/v1/messages/${data.uid}/attachments/${data.index}?${params}`,
      { token: data.token },
    );
  });

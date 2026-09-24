export type Address = { name: string; email: string };

export type Folder = {
  name: string;
  path: string;
  role: string;
};

export type Attachment = {
  index: number;
  filename: string;
  content_type: string;
  size: number;
};

export type MediaPart = {
  content_type: string;
  filename?: string;
};

export type MailSummary = {
  uid: string;
  folder: string;
  from: Address;
  to: Address[];
  cc: Address[];
  subject: string;
  date: string | null;
  dateLabel?: string;
  message_id?: string;
  seen: boolean;
  preview: string;
  has_attachments?: boolean;
  media?: MediaPart[];
  size?: number;
  order?: number;
};

export type MailMessage = MailSummary & {
  text: string;
  text_from_html?: boolean;
  attachments: Attachment[];
};

export type MailPage = {
  folder: string;
  folder_name: string;
  total: number;
  page: number;
  limit: number;
  messages: MailSummary[];
};

export type SessionInfo = {
  token: string;
  email: string;
  hosts: {
    imap_host: string;
    imap_port: number;
    smtp_host: string;
    smtp_ssl_port: number;
  };
  folders: Folder[];
};

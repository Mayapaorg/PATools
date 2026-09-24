const BASE = process.env.GMX_API_URL ?? "http://127.0.0.1:8765";

type BridgeInit = {
  method?: string;
  token?: string | null;
  body?: unknown;
};

export async function gmxRequest<T>(path: string, init: BridgeInit = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.token) headers.Authorization = `Bearer ${init.token}`;
  if (init.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method: init.method ?? "GET",
      headers,
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      signal: AbortSignal.timeout(40_000),
    });
  } catch {
    throw new Error(
      "The mail bridge is offline, so this desk cannot reach GMX right now. Sample mail still works.",
    );
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { error: text.slice(0, 300) };
    }
  }
  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "error" in payload && typeof payload.error === "string"
        ? payload.error
        : `The mail bridge returned ${response.status}.`;
    throw new Error(message);
  }
  return payload as T;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// No auth in this demo — session_id is a client-generated anonymous
// identity, persisted per-browser so different visitors (or the same
// visitor in a different browser/incognito window) never see each other's
// documents. Sent as an X-Session-Id header on every request except the SSE
// events endpoint, which uses a query param instead since native
// EventSource can't set custom headers.
function getSessionId(): string {
  const key = "docflow_session_id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

export type DocumentStatus = "queued" | "processing" | "done" | "failed";

export interface ExtractedFields {
  document_type: string;
  key_dates: string[];
  parties: string[];
  summary: string;
  confidence: number;
}

export interface DocumentRecord {
  id: string;
  filename: string;
  status: DocumentStatus;
  created_at: number;
  attempts: number;
  error: string | null;
  extracted: ExtractedFields | null;
  text_preview: string | null;
}

export interface SearchResult {
  id: string;
  filename: string;
  document_type: string;
  summary: string;
  score: number;
}

export interface ChatSource {
  id: string;
  filename: string;
  score: number;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
}

export async function uploadDocument(file: File): Promise<DocumentRecord> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/documents`, {
    method: "POST",
    headers: { "X-Session-Id": getSessionId() },
    body: formData,
  });
  if (!res.ok) {
    throw new Error(`Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchDocument(id: string): Promise<DocumentRecord> {
  const res = await fetch(`${API_BASE}/documents/${id}`, {
    headers: { "X-Session-Id": getSessionId() },
  });
  if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);
  return res.json();
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/documents/${id}`, {
    method: "DELETE",
    headers: { "X-Session-Id": getSessionId() },
  });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}

export async function clearAllDocuments(): Promise<void> {
  const res = await fetch(`${API_BASE}/documents`, {
    method: "DELETE",
    headers: { "X-Session-Id": getSessionId() },
  });
  if (!res.ok) throw new Error(`Clear all failed: ${res.status}`);
}

export async function searchDocuments(query: string): Promise<SearchResult[]> {
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`, {
    headers: { "X-Session-Id": getSessionId() },
  });
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
}

export async function askQuestion(query: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Session-Id": getSessionId() },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error(`Chat failed: ${res.status}`);
  return res.json();
}

/**
 * Subscribes to a document's SSE progress stream.
 * Returns an unsubscribe function.
 */
export function subscribeToDocumentEvents(
  id: string,
  onEvent: (eventName: string, data: any) => void
): () => void {
  // EventSource can't set custom headers, so the session id travels as a
  // query param here instead of the X-Session-Id header used everywhere else.
  const source = new EventSource(
    `${API_BASE}/documents/${id}/events?session_id=${encodeURIComponent(getSessionId())}`
  );

  const handler = (eventName: string) => (evt: MessageEvent) => {
    let data: any;
    try {
      data = JSON.parse(evt.data);
    } catch {
      data = evt.data;
    }
    onEvent(eventName, data);

    // The backend ends the HTTP response on a terminal status, but a native
    // EventSource treats that as a dropped connection and auto-reconnects
    // (replaying the same terminal status forever) unless we close it here.
    if (eventName === "status" && (data?.status === "done" || data?.status === "failed")) {
      source.close();
    }
  };

  source.addEventListener("status", handler("status"));
  source.addEventListener("progress", handler("progress"));
  source.onerror = () => {
    // In production: reconnect with backoff. For this demo, terminal
    // statuses close the connection explicitly above.
  };

  return () => source.close();
}

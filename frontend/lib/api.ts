const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

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

export async function uploadDocument(file: File): Promise<DocumentRecord> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/documents`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    throw new Error(`Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchDocument(id: string): Promise<DocumentRecord> {
  const res = await fetch(`${API_BASE}/documents/${id}`);
  if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);
  return res.json();
}

export async function searchDocuments(query: string): Promise<SearchResult[]> {
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
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
  const source = new EventSource(`${API_BASE}/documents/${id}/events`);

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

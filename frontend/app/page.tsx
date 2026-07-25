"use client";

import { useCallback, useRef, useState } from "react";
import {
  ChatSource,
  DocumentRecord,
  SearchResult,
  subscribeToDocumentEvents,
  uploadDocument,
  searchDocuments,
  askQuestion,
  deleteDocument,
  clearAllDocuments,
} from "@/lib/api";

interface TrackedDoc extends DocumentRecord {
  log: string[];
}

interface ChatMessage {
  role: "user" | "assistant" | "error";
  content: string;
  sources?: ChatSource[];
}

export default function Home() {
  const [docs, setDocs] = useState<Record<string, TrackedDoc>>({});
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [asking, setAsking] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    const record = await uploadDocument(file);
    setDocs((prev) => ({ ...prev, [record.id]: { ...record, log: ["queued"] } }));

    subscribeToDocumentEvents(record.id, (eventName, data) => {
      setDocs((prev) => {
        const current = prev[record.id];
        if (!current) return prev;
        const next: TrackedDoc = { ...current, log: [...current.log] };

        if (eventName === "status" && data.status) {
          next.status = data.status;
          next.log.push(`status: ${data.status}`);
          if (data.error) next.error = data.error;
        }
        if (eventName === "status" && data.id) {
          // full record replay on connect
          Object.assign(next, data);
        }
        if (eventName === "progress" && data.step) {
          next.log.push(`progress: ${data.step}`);
        }
        return { ...prev, [record.id]: next };
      });
    });
  }, []);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const runSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await searchDocuments(query);
      setResults(res);
    } finally {
      setSearching(false);
    }
  };

  const askChat = async () => {
    if (!chatInput.trim() || asking) return;
    const question = chatInput.trim();
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", content: question }]);
    setAsking(true);
    try {
      const res = await askQuestion(question);
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.answer, sources: res.sources },
      ]);
    } catch {
      setChatMessages((prev) => [
        ...prev,
        { role: "error", content: "Something went wrong asking that question. Try again." },
      ]);
    } finally {
      setAsking(false);
    }
  };

  const handleDelete = async (id: string) => {
    await deleteDocument(id);
    setDocs((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  const handleClearAll = async () => {
    if (!window.confirm("Delete all documents you've uploaded in this browser? This can't be undone.")) return;
    await clearAllDocuments();
    setDocs({});
  };

  const docList = Object.values(docs).sort((a, b) => b.created_at - a.created_at);

  return (
    <div className="container">
      <h1>DocFlow</h1>
      <p className="subtitle">
        Async document pipeline: upload → extract → search, with real-time progress over SSE.
      </p>

      <div className="panel">
        <div
          className="dropzone"
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={onDrop}
        >
          Drop a PDF here, or click to choose one
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
            e.target.value = "";
          }}
        />
      </div>

      {docList.length > 0 && (
        <div className="panel">
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
            <button className="btn-link-danger" onClick={handleClearAll}>
              Clear all
            </button>
          </div>
          {docList.map((doc) => (
            <div key={doc.id} className="doc-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <strong>{doc.filename}</strong>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span className={`badge badge-${doc.status}`}>{doc.status}</span>
                  <button className="btn-link-danger" onClick={() => handleDelete(doc.id)}>
                    delete
                  </button>
                </div>
              </div>
              <div className="progress-log">
                {doc.log.map((line, i) => (
                  <div key={i}>› {line}</div>
                ))}
              </div>
              {doc.status === "failed" && doc.error && (
                <div className="result-card" style={{ color: "var(--err)" }}>
                  {doc.error}
                </div>
              )}
              {doc.extracted && (
                <div className="result-card">
                  <div>
                    <strong>{doc.extracted.document_type}</strong>{" "}
                    <span style={{ color: "var(--muted)", fontSize: 12 }}>
                      confidence {doc.extracted.confidence}
                    </span>
                  </div>
                  <div className="result-summary">{doc.extracted.summary}</div>
                  {doc.extracted.key_dates.length > 0 && (
                    <div className="result-summary">Dates: {doc.extracted.key_dates.join(", ")}</div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="panel">
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            placeholder="Search processed documents…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch()}
          />
        </div>
        {searching && <div className="progress-log">searching…</div>}
        {results && results.length === 0 && <div className="progress-log">No matches.</div>}
        {results?.map((r) => (
          <div key={r.id} className="result-card">
            <strong>{r.filename}</strong> — {r.document_type}{" "}
            <span style={{ color: "var(--muted)", fontSize: 12 }}>score {r.score}</span>
            <div className="result-summary">{r.summary}</div>
          </div>
        ))}
      </div>

      <div className="panel">
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            placeholder="Ask a question about your documents…"
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && askChat()}
          />
        </div>
        {chatMessages.length > 0 && (
          <div style={{ marginTop: 12 }}>
            {chatMessages.map((m, i) => (
              <div
                key={i}
                className={`chat-bubble chat-bubble-${m.role}`}
              >
                {m.content}
                {m.sources && m.sources.length > 0 && (
                  <div style={{ marginTop: 6 }}>
                    {m.sources.map((s) => (
                      <span key={s.id} className="chat-source-tag">
                        {s.filename}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        {asking && <div className="progress-log">thinking…</div>}
      </div>
    </div>
  );
}

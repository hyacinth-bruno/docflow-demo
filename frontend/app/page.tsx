"use client";

import { useCallback, useRef, useState } from "react";
import {
  DocumentRecord,
  SearchResult,
  subscribeToDocumentEvents,
  uploadDocument,
  searchDocuments,
} from "@/lib/api";

interface TrackedDoc extends DocumentRecord {
  log: string[];
}

export default function Home() {
  const [docs, setDocs] = useState<Record<string, TrackedDoc>>({});
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
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
          {docList.map((doc) => (
            <div key={doc.id} className="doc-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <strong>{doc.filename}</strong>
                <span className={`badge badge-${doc.status}`}>{doc.status}</span>
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
    </div>
  );
}

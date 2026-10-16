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

const Icon = ({ name }: { name: "spark" | "upload" | "search" | "send" | "file" | "check" | "arrow" }) => {
  const paths = {
    spark: <><path d="m12 3-1.2 5.8L5 10l5.8 1.2L12 17l1.2-5.8L19 10l-5.8-1.2L12 3Z" /><path d="m19 16-.5 2.5L16 19l2.5.5L19 22l.5-2.5L22 19l-2.5-.5L19 16Z" /></>,
    upload: <><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M5 20h14" /></>,
    search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></>,
    send: <><path d="m21 3-7.5 18-3.5-7-7-3.5L21 3Z" /><path d="M10 14 21 3" /></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
};

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
        if (eventName === "status" && data.id) Object.assign(next, data);
        if (eventName === "progress" && data.step) next.log.push(`progress: ${data.step}`);
        return { ...prev, [record.id]: next };
      });
    });
  }, []);

  const runSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try { setResults(await searchDocuments(query)); } finally { setSearching(false); }
  };

  const askChat = async () => {
    if (!chatInput.trim() || asking) return;
    const question = chatInput.trim();
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", content: question }]);
    setAsking(true);
    try {
      const res = await askQuestion(question);
      setChatMessages((prev) => [...prev, { role: "assistant", content: res.answer, sources: res.sources }]);
    } catch {
      setChatMessages((prev) => [...prev, { role: "error", content: "Something went wrong asking that question. Try again." }]);
    } finally { setAsking(false); }
  };

  const handleDelete = async (id: string) => {
    await deleteDocument(id);
    setDocs((prev) => { const next = { ...prev }; delete next[id]; return next; });
  };

  const handleClearAll = async () => {
    if (!window.confirm("Delete all documents you've uploaded in this browser? This can't be undone.")) return;
    await clearAllDocuments();
    setDocs({});
  };

  const docList = Object.values(docs).sort((a, b) => b.created_at - a.created_at);
  const processedCount = docList.filter((doc) => doc.status === "done").length;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark"><Icon name="spark" /></span><span>Doc<span className="brand-accent">Flow</span></span></div>
        <div className="status-pill"><span className="status-dot" /> Pipeline online</div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow"><Icon name="spark" /> Your intelligent document workspace</p>
          <h1>Make every document<br /><em>work harder.</em></h1>
          <p className="hero-copy">Upload, understand, and find what matters — all in one beautifully simple workflow.</p>
        </div>
        <div className="hero-orbit" aria-hidden="true"><span /><span /><span /></div>
      </section>

      <section className="upload-card" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const file = e.dataTransfer.files?.[0]; if (file) handleFile(file); }}>
        <div className="upload-icon"><Icon name="upload" /></div>
        <div className="upload-content">
          <h2>Bring your documents to life</h2>
          <p>Drop a PDF here, or <button className="inline-button" onClick={() => fileInputRef.current?.click()}>browse your files</button></p>
          <small>PDF files up to 25 MB</small>
        </div>
        <button className="primary-button" onClick={() => fileInputRef.current?.click()}>Upload PDF <Icon name="arrow" /></button>
        <input ref={fileInputRef} type="file" accept="application/pdf" hidden onChange={(e) => { const file = e.target.files?.[0]; if (file) handleFile(file); e.target.value = ""; }} />
      </section>

      <section className="stats-grid">
        <div className="stat-card"><span className="stat-label">TOTAL DOCUMENTS</span><strong>{docList.length}</strong><span className="stat-note">in your workspace</span></div>
        <div className="stat-card"><span className="stat-label">PROCESSED</span><strong>{processedCount}</strong><span className="stat-note positive"><Icon name="check" /> ready to search</span></div>
        <div className="stat-card"><span className="stat-label">AI ASSISTANT</span><strong className="stat-live"><span className="status-dot" /> Ready</strong><span className="stat-note">ask anything about your files</span></div>
      </section>

      <div className="workspace-grid">
        <section className="panel library-panel">
          <div className="panel-heading"><div><p className="eyebrow">Your workspace</p><h2>Document library</h2></div>{docList.length > 0 && <button className="text-button" onClick={handleClearAll}>Clear all</button>}</div>
          {docList.length === 0 ? <div className="empty-state"><div className="empty-icon"><Icon name="file" /></div><strong>Your library is waiting</strong><p>Upload your first document to see its extracted insights here.</p></div> : <div className="document-list">
            {docList.map((doc) => <article key={doc.id} className="document-item">
              <div className="file-icon"><Icon name="file" /></div>
              <div className="document-info"><div className="document-title"><strong>{doc.filename}</strong><span className={`badge badge-${doc.status}`}>{doc.status}</span></div>
                {doc.extracted ? <><p>{doc.extracted.summary}</p><span className="document-meta">{doc.extracted.document_type} · {Math.round(doc.extracted.confidence * 100)}% confidence</span></> : <div className="progress-log">{doc.log[doc.log.length - 1] || "processing…"}</div>}
                {doc.status === "failed" && doc.error && <p className="error-text">{doc.error}</p>}
              </div>
              <button className="delete-button" onClick={() => handleDelete(doc.id)} aria-label={`Delete ${doc.filename}`}>×</button>
            </article>)}
          </div>}
        </section>

        <div className="side-stack">
          <section className="panel tool-panel">
            <div className="panel-heading compact"><div><p className="eyebrow"><Icon name="search" /> Explore</p><h2>Search your docs</h2></div></div>
            <div className="input-wrap"><Icon name="search" /><input type="text" placeholder="Find a document or topic…" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && runSearch()} /><button onClick={runSearch} disabled={searching}>{searching ? "…" : "Search"}</button></div>
            {results && (results.length ? results.map((r) => <div key={r.id} className="search-result"><strong>{r.filename}</strong><span>{r.document_type}</span><p>{r.summary}</p></div>) : <p className="muted-message">No matches found.</p>)}
          </section>

          <section className="panel tool-panel assistant-panel">
            <div className="assistant-heading"><div className="assistant-avatar"><Icon name="spark" /></div><div><p className="eyebrow">Powered by AI</p><h2>Ask your assistant</h2></div></div>
            {chatMessages.length === 0 && <p className="assistant-intro">Ask questions across your entire document library and get answers with context.</p>}
            {chatMessages.map((m, i) => <div key={i} className={`chat-bubble chat-bubble-${m.role}`}>{m.content}{m.sources?.length ? <div className="source-list">{m.sources.map((s) => <span key={s.id} className="chat-source-tag">{s.filename}</span>)}</div> : null}</div>)}
            {asking && <div className="thinking"><span /><span /><span /> thinking</div>}
            <div className="chat-input-wrap"><input type="text" placeholder="What would you like to know?" value={chatInput} onChange={(e) => setChatInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && askChat()} /><button onClick={askChat} disabled={asking || !chatInput.trim()} aria-label="Ask assistant"><Icon name="send" /></button></div>
          </section>
        </div>
      </div>
      <footer>DocFlow <span>·</span> Secure, private document intelligence</footer>
    </main>
  );
}

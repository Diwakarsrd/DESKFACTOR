import { useState } from "react";
import Icon from "./Icon.jsx";

const TYPE_ICON = { pdf: "pdf", image: "image", text: "text" };

function when(s) {
  const d = new Date(s);
  const mins = Math.round((Date.now() - d) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 24 * 60) return `${Math.round(mins / 60)} h ago`;
  return d.toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
}

const label = (a) => a.filename || (a.input_type === "text" ? "Pasted text" : `${a.input_type} upload`);

export default function History({ items, activeId, onOpen, onNew }) {
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const shown = needle
    ? items.filter((a) => `${label(a)} ${a.summary || ""} ${a.status}`.toLowerCase().includes(needle))
    : items;

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2 className="card-title">Previous reports</h2>
          <p className="card-sub">{items.length} saved</p>
        </div>
        {activeId && (
          <button type="button" className="btn" onClick={onNew}>
            <Icon name="plus" /> New
          </button>
        )}
      </div>

      {items.length > 3 && (
        <div className="search">
          <Icon name="search" />
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search reports" aria-label="Search reports" />
        </div>
      )}

      {items.length === 0 ? (
        <p className="empty-small">No analyses yet. Your reports will appear here.</p>
      ) : shown.length === 0 ? (
        <p className="empty-small">No reports match “{q}”.</p>
      ) : (
        <ul className="history-list" aria-label="Previous reports">
          {shown.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                className={`history-item${a.id === activeId ? " on" : ""}`}
                onClick={() => onOpen(a.id)}
                aria-current={a.id === activeId ? "true" : undefined}
              >
                <div className="history-top">
                  <span className="history-name">
                    <Icon name={TYPE_ICON[a.input_type] || "file"} />
                    <span>{label(a)}</span>
                  </span>
                  <span className={`pill ${a.status}`}>{a.status}</span>
                </div>
                {a.status === "failed" ? (
                  <span className="history-snip err">{a.error || "Processing failed"}</span>
                ) : a.summary ? (
                  <span className="history-snip">{a.summary}</span>
                ) : null}
                <span className="history-when" title={new Date(a.created_at).toLocaleString()}>{when(a.created_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

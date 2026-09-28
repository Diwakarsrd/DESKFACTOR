import { useCallback, useEffect, useState } from "react";
import { getAnalysis, listAnalyses } from "./api.js";
import SubmitForm from "./components/SubmitForm.jsx";
import History from "./components/History.jsx";
import ReportView from "./components/ReportView.jsx";

export default function App() {
  const [history, setHistory] = useState([]);
  const [active, setActive] = useState(null);
  const [error, setError] = useState("");

  const refresh = useCallback(() =>
    listAnalyses().then(setHistory).catch((e) => setError(e.message)),
    []
  );

  useEffect(() => { refresh(); }, [refresh]);

  // Poll the open report until it finishes.
  useEffect(() => {
    if (!active || active.status !== "processing") return;
    const t = setInterval(async () => {
      try {
        const a = await getAnalysis(active.id);
        setActive(a);
        if (a.status !== "processing") refresh();
      } catch (e) { setError(e.message); }
    }, 1800);
    return () => clearInterval(t);
  }, [active, refresh]);

  const open = async (id) => {
    setError("");
    try { setActive(await getAnalysis(id)); } catch (e) { setError(e.message); }
  };

  return (
    <div className="shell">
      <header className="top">
        <div className="top-brand">
          <div className="top-logo">
            {/* Medical cross / document icon */}
            <svg viewBox="0 0 24 24">
              <path d="M9 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9l-6-6z" />
              <polyline points="13 3 13 9 19 9" />
              <line x1="12" y1="13" x2="12" y2="17" />
              <line x1="10" y1="15" x2="14" y2="15" />
            </svg>
          </div>
          <div>
            <h1>Clinical<span>AI</span></h1>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 1 }}>Intelligent Document Reviewer</div>
          </div>
        </div>
        <div className="top-meta">
          <p className="top-sub">
            Submit clinical notes, scans or PDFs · Get a structured evidence-backed report
          </p>
          <span className="top-disclaimer">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            Synthetic data only · Does not replace clinical judgement
          </span>
        </div>
      </header>

      <main className="grid">
        <section className="left">
          <SubmitForm
            onCreated={(id) => { refresh(); open(id); }}
            onError={setError}
          />
          <History items={history} activeId={active?.id} onOpen={open} />
        </section>

        <section className="right">
          {error && (
            <div className="banner error" role="alert">
              <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
              <span>{error}</span>
            </div>
          )}
          {!active && !error && (
            <div className="empty-state">
              <div className="empty-icon">
                <svg viewBox="0 0 24 24">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
              </div>
              <h2>No report open</h2>
              <p>Submit a clinical document on the left, or open a previous report from the history panel.</p>
            </div>
          )}
          {active && <ReportView a={active} />}
        </section>
      </main>
    </div>
  );
}

import { useEffect, useState } from "react";
import Icon from "./Icon.jsx";

// Mirrors the backend's `stage` values (see backend/app/main.py and pipeline.py).
const STEPS = [
  { label: "Reading document", stages: ["Queued", "Reading document"] },
  { label: "Extracting clinical information", stages: ["Extracting clinical information"] },
  { label: "Verifying against the source", stages: ["Verifying against source text"] },
  { label: "Running safety checks", stages: ["Running safety checks"] },
  { label: "Writing the summary", stages: ["Writing summary"] },
];

const inputLabel = (a) => a.filename || (a.input_type === "text" ? "Pasted text" : `${a.input_type} upload`);

function useElapsed(since) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return Math.max(0, Math.round((now - new Date(since)) / 1000));
}

function Processing({ a }) {
  const secs = useElapsed(a.created_at);
  const idx = Math.max(0, STEPS.findIndex((s) => s.stages.includes(a.stage)));
  return (
    <div className="card processing" aria-live="polite" aria-busy="true">
      <div className="processing-head">
        <div className="spinner" />
        <div>
          <h2>Analysing {inputLabel(a)}</h2>
          <p>{secs}s elapsed</p>
        </div>
      </div>
      <ol className="stepper">
        {STEPS.map((s, i) => (
          <li key={s.label} className={i < idx ? "done" : i === idx ? "active" : ""}>
            <span className="step-dot">{i < idx && <Icon name="check" />}</span>
            {s.label}
          </li>
        ))}
      </ol>
      <p className="processing-note">
        Usually takes 10–40 seconds. Scanned and handwritten documents take longer. You can open other reports meanwhile.
      </p>
    </div>
  );
}

function Failed({ a, onNew }) {
  const e = (a.error || "").toLowerCase();
  const fileIssue = /blurry|readable|corrupt|password|image could not/.test(e);
  const aiIssue = /ai |rate-limited|timed out|reach/.test(e);
  return (
    <div className="card failed-card" role="alert">
      <div className="failed-icon"><Icon name="xCircle" /></div>
      <h2>This document could not be processed</h2>
      <p>{a.error || "Something went wrong."}</p>
      {(fileIssue || aiIssue) && (
        <ul className="tips">
          {fileIssue && <li>Photograph the page flat, in good light, filling the frame.</li>}
          {fileIssue && <li>If you have the text, paste it into the Text tab instead.</li>}
          {aiIssue && <li>This is usually temporary. Wait a moment and submit again.</li>}
        </ul>
      )}
      <p className="meta">{inputLabel(a)} · submitted {new Date(a.created_at).toLocaleString()}</p>
      <button type="button" className="btn" onClick={onNew}><Icon name="plus" /> Start a new analysis</button>
    </div>
  );
}

const Conf = ({ c }) => <span className={`conf ${c}`} title={`${c} confidence`}>{c}</span>;

function Section({ id, title, icon, count, tone = "", open = true, children }) {
  return (
    <details id={id} className={`sec${tone ? ` tone-${tone}` : ""}`} open={open}>
      <summary>
        <span className="sec-icon"><Icon name={icon} /></span>
        {title}
        {count !== undefined && <span className="count">{count}</span>}
      </summary>
      <div className="sec-body">{children}</div>
    </details>
  );
}

function Facts({ items, empty }) {
  if (!items?.length) return <p className="sec-empty">{empty}</p>;
  return (
    <ul className="facts">
      {items.map((it, i) => (
        <li key={i} className="fact">
          <div className="fact-top">
            <span className="fact-name">{it.name}</span>
            {it.detail && <span className="fact-detail">{it.detail}</span>}
            <Conf c={it.confidence} />
          </div>
          {it.evidence && <div className="evidence">“{it.evidence}”</div>}
        </li>
      ))}
    </ul>
  );
}

function Vitals({ items }) {
  if (!items?.length) return <p className="sec-empty">No vital signs were documented.</p>;
  return (
    <div className="vitals">
      {items.map((v, i) => (
        <div key={i} className={`vital${v.flag ? " flagged" : ""}`} title={v.evidence ? `“${v.evidence}”` : undefined}>
          <div className="vital-name">{v.name}</div>
          <div className="vital-value">{v.value}{v.unit && <small>{v.unit}</small>}</div>
          {v.flag && <div className="vital-flag">{v.flag}</div>}
          {v.confidence !== "high" && <div className="vital-ev">{v.confidence} confidence</div>}
        </div>
      ))}
    </div>
  );
}

function Plain({ list, icon, empty }) {
  if (!list?.length) return <p className="sec-empty">{empty}</p>;
  return (
    <ul className="plain">
      {list.map((x, i) => (
        <li key={i}>
          <Icon name={icon} />
          <div className="plain-body">
            {typeof x === "string" ? x : x.description}
            {x.source === "rules" && <span className="src-tag" title="Found by a deterministic rule check, not the AI">rule</span>}
            {x.evidence && <div className="evidence">“{x.evidence}”</div>}
          </div>
        </li>
      ))}
    </ul>
  );
}

function jump(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.open = true;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function download(a) {
  const data = { id: a.id, created_at: a.created_at, completed_at: a.completed_at, input: inputLabel(a), warnings: a.warnings, ...a.report };
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const link = Object.assign(document.createElement("a"), { href: url, download: `clinical-report-${a.id.slice(0, 8)}.json` });
  link.click();
  URL.revokeObjectURL(url);
}

function printReport() {
  document.querySelectorAll(".report details").forEach((d) => { d.open = true; });
  window.print();
}

export default function ReportView({ a, onNew }) {
  if (a.status === "processing") return <Processing a={a} />;
  if (a.status === "failed") return <Failed a={a} onNew={onNew} />;

  const r = a.report || {};
  const pi = Object.entries(r.patient_information || {}).filter(([, v]) => v);
  const flagged = (r.vitals || []).filter((v) => v.flag).length;
  const tiles = [
    { id: "sec-review", n: r.requires_review?.length || 0, label: "Need review", tone: "warn" },
    { id: "sec-vitals", n: flagged, label: "Flagged vitals", tone: "bad" },
    { id: "sec-incons", n: r.potential_inconsistencies?.length || 0, label: "Inconsistencies", tone: "bad" },
    { id: "sec-missing", n: r.missing_information?.length || 0, label: "Missing info", tone: "info" },
  ];

  return (
    <article className="report">
      <header className="report-head">
        <div>
          <h2>Clinical review</h2>
          <div className="report-meta">
            <span className="pill completed">completed</span>
            <span>{inputLabel(a)}</span>
            <span aria-hidden="true">·</span>
            <span>{new Date(a.completed_at || a.created_at).toLocaleString()}</span>
          </div>
        </div>
        <div className="report-actions">
          <button type="button" className="btn" onClick={printReport}><Icon name="printer" /> Print</button>
          <button type="button" className="btn" onClick={() => download(a)}><Icon name="download" /> JSON</button>
        </div>
      </header>

      <section className="summary" aria-label="Report summary">
        <h3>Report summary</h3>
        <p>{a.summary || r.report_summary || "No summary available."}</p>
      </section>

      <div className="glance">
        {tiles.map((t) => (
          <button key={t.id} type="button" className={`glance-tile ${t.n ? t.tone : "zero"}`} onClick={() => jump(t.id)} disabled={!t.n}>
            <div className="glance-num">{t.n}</div>
            <div className="glance-label">{t.label}</div>
          </button>
        ))}
      </div>

      {(a.warnings || []).map((w, i) => (
        <div key={i} className="banner warn"><Icon name="warn" /><span>{w}</span></div>
      ))}

      {r.requires_review?.length > 0 && (
        <Section id="sec-review" title="Items requiring review" icon="flag" count={r.requires_review.length} tone="warn">
          <Plain list={r.requires_review} icon="flag" />
        </Section>
      )}

      <h3 className="sec-group-title">Clinical details</h3>

      <Section id="sec-patient" title="Patient information" icon="user">
        {pi.length ? (
          <dl className="patient">
            {pi.map(([k, v]) => (
              <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{v}</dd></div>
            ))}
          </dl>
        ) : <p className="sec-empty">No patient details were found in the document.</p>}
      </Section>

      <Section id="sec-vitals" title="Vital signs" icon="activity" count={r.vitals?.length || 0}>
        <Vitals items={r.vitals} />
      </Section>
      <Section title="Symptoms" icon="thermometer" count={r.symptoms?.length || 0}>
        <Facts items={r.symptoms} empty="No symptoms were documented." />
      </Section>
      <Section title="Diagnoses & conditions" icon="clipboard" count={r.diagnoses?.length || 0}>
        <Facts items={r.diagnoses} empty="No diagnoses or conditions were documented." />
      </Section>
      <Section title="Medications" icon="pill" count={r.medications?.length || 0}>
        <Facts items={r.medications} empty="No medications were documented." />
      </Section>
      <Section title="Allergies" icon="ban" count={r.allergies?.length || 0}>
        <Facts items={r.allergies} empty="Allergy status was not documented." />
      </Section>
      <Section title="Clinical observations" icon="eye" count={r.clinical_observations?.length || 0}>
        <Facts items={r.clinical_observations} empty="No examination findings or observations were documented." />
      </Section>
      <Section title="Clinical concerns" icon="warn" count={r.clinical_concerns?.length || 0}>
        <Facts items={r.clinical_concerns} empty="No specific concerns were identified from the documented findings." />
      </Section>

      <h3 className="sec-group-title">Quality checks</h3>

      <Section id="sec-incons" title="Potential inconsistencies" icon="shuffle" count={r.potential_inconsistencies?.length || 0} tone={r.potential_inconsistencies?.length ? "bad" : ""}>
        <Plain list={r.potential_inconsistencies} icon="shuffle" empty="No inconsistencies were detected." />
      </Section>
      <Section id="sec-missing" title="Missing or incomplete information" icon="help" count={r.missing_information?.length || 0} tone="info">
        <Plain list={r.missing_information} icon="help" empty="No important gaps were detected." />
      </Section>

      {a.source_preview && (
        <Section title="Source text used for analysis" icon="file" open={false}>
          <pre className="source-pre">{a.source_preview}</pre>
        </Section>
      )}

      <p className="disclaimer">AI-assisted review of synthetic data. Every finding is quoted from the source; verify before any clinical use.</p>
    </article>
  );
}

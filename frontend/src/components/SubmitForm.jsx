import { useEffect, useState } from "react";
import { submitFile, submitText } from "../api.js";
import Icon from "./Icon.jsx";

const MAX_MB = 10;
const MAX_CHARS = 20000;

const TABS = [
  { id: "text", label: "Text", icon: "text" },
  { id: "image", label: "Image", icon: "image" },
  { id: "pdf", label: "PDF", icon: "pdf" },
];

const ACCEPT = {
  image: { attr: "image/png,image/jpeg,image/webp", types: ["image/png", "image/jpeg", "image/webp"], hint: "PNG, JPG or WebP · typed, scanned or handwritten" },
  pdf: { attr: "application/pdf,.pdf", types: ["application/pdf"], hint: "Typed or scanned PDF · first 8 pages are read" },
};

// All synthetic.
const SAMPLES = {
  "Complete note": `SYNTHETIC DATA - NOT A REAL PATIENT
Patient: Jane Doe, DOB: 1975-03-14, MRN: 100423
Date: 2024-11-08  Clinician: Dr. A. Smith

CC: Productive cough x 5 days, fever, shortness of breath on exertion.

Vitals: BP 128/82 mmHg, HR 98 bpm, RR 22/min, Temp 38.6°C, SpO2 93%

PMH: Type 2 diabetes mellitus (on metformin 500mg BD), Hypertension.
Allergies: Penicillin (rash)

Exam: Dullness to percussion R base. Bronchial breathing R lower zone.
CXR: Consolidation right lower lobe consistent with pneumonia.

Assessment: Community-acquired pneumonia.
Plan: Azithromycin 500mg OD x 5 days. Increase fluids. Follow up in 3 days.`,
  "Conflicts & allergy": `SYNTHETIC DATA - NOT A REAL PATIENT
Patient: Meera Iyer, 62 F. DOB: 04/09/1968.
Allergies: Penicillin - anaphylaxis (2019).
Presenting with sore throat and fever 39.2 C for 2 days. HR 122, BP 96/58, SpO2 97%.
History: No history of hypertension. Currently taking amlodipine 5 mg daily for hypertension.
Assessment: Streptococcal pharyngitis. Started amoxicillin 500 mg TID for 7 days.
Patient reports she has been afebrile since admission. Temp charted 39.2 C.
Note: Cafeteria menu changed to include new vegetarian options next week.`,
  "Sparse note": `SYNTHETIC DATA - NOT A REAL PATIENT
Pt c/o headaches x 2 wks, worse in mornings. Some nausea. Started "something for pain" from pharmacy.
BP today 150/96. Advised to rest. F/u if worse.`,
};

const fmtSize = (b) => (b < 1024 * 1024 ? `${Math.round(b / 1024)} KB` : `${(b / 1024 / 1024).toFixed(1)} MB`);

export default function SubmitForm({ onCreated, onError }) {
  const [tab, setTab] = useState("text");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!file || !file.type.startsWith("image/")) { setPreview(""); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const switchTab = (id) => {
    setTab(id);
    if (file && id !== "text" && !ACCEPT[id].types.includes(file.type)) setFile(null);
  };

  const pick = (f) => {
    if (!f) return;
    onError("");
    const kind = f.type === "application/pdf" ? "pdf" : ACCEPT.image.types.includes(f.type) ? "image" : null;
    if (!kind) return onError("Unsupported file type. Upload a PDF, PNG, JPG or WebP file.");
    if (f.size === 0) return onError("That file is empty.");
    if (f.size > MAX_MB * 1024 * 1024) return onError(`File is ${fmtSize(f.size)}; the limit is ${MAX_MB} MB.`);
    setTab(kind);
    setFile(f);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files?.[0]);
  };

  const submit = async (e) => {
    e.preventDefault();
    onError("");
    if (tab === "text") {
      const t = text.trim();
      if (!t) return onError("Enter some clinical text first.");
      if (t.length < 20) return onError("The text is too short to analyse. Add more clinical detail.");
      if (t.length > MAX_CHARS) return onError(`Text is longer than ${MAX_CHARS.toLocaleString()} characters.`);
    } else if (!file) {
      return onError(`Choose ${tab === "pdf" ? "a PDF" : "an image"} to upload.`);
    }
    setBusy(true);
    try {
      const r = tab === "text" ? await submitText(text) : await submitFile(file);
      onCreated(r.id);
      if (tab === "text") setText(""); else setFile(null);
    } catch (err) {
      onError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const over = text.length > MAX_CHARS;

  return (
    <form className="card" onSubmit={submit} noValidate>
      <div className="card-head">
        <div>
          <h2 className="card-title">New analysis</h2>
          <p className="card-sub">Paste notes or upload a document</p>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Input type">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => switchTab(t.id)}>
            <Icon name={t.icon} /> {t.label}
          </button>
        ))}
      </div>

      {tab === "text" ? (
        <>
          <label htmlFor="clinical-text" className="sr-only">Clinical notes</label>
          <textarea
            id="clinical-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={10}
            placeholder="Paste clinical notes here (synthetic data only)…"
            spellCheck={false}
          />
          <div className="field-foot">
            <div className="samples">
              <span className="samples-label">Try:</span>
              {Object.keys(SAMPLES).map((k) => (
                <button key={k} type="button" className="chip-btn" onClick={() => setText(SAMPLES[k])}>{k}</button>
              ))}
            </div>
            <span className={`char-count${over ? " over" : ""}`}>{text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}</span>
          </div>
        </>
      ) : (
        <>
          <label
            className={`drop${dragging ? " dragging" : ""}${file ? " has-file" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <input
              type="file"
              accept={ACCEPT[tab].attr}
              onChange={(e) => { pick(e.target.files[0]); e.target.value = ""; }}
              aria-label={`Upload ${tab === "pdf" ? "a PDF" : "an image"}`}
            />
            {file ? (
              <div className="file-preview">
                {preview ? <img src={preview} alt="Preview of the selected document" /> : <div className="drop-icon"><Icon name="pdf" /></div>}
                <div>
                  <div className="file-name">{file.name}</div>
                  <div className="file-meta">{fmtSize(file.size)} · click or drop to replace</div>
                </div>
                <button type="button" className="file-clear" onClick={(e) => { e.preventDefault(); setFile(null); }}>Remove</button>
              </div>
            ) : (
              <div>
                <div className="drop-icon"><Icon name="upload" /></div>
                <div className="drop-label">Drop {tab === "pdf" ? "a PDF" : "an image"} here or click to browse</div>
                <div className="drop-hint">{ACCEPT[tab].hint} · max {MAX_MB} MB</div>
              </div>
            )}
          </label>
          <p className="input-note">Blurry or partly unreadable pages are flagged rather than guessed.</p>
        </>
      )}

      <button className="primary" disabled={busy || over} aria-busy={busy}>
        {busy ? <><span className="btn-spinner" /> Uploading…</> : "Analyse document"}
      </button>
    </form>
  );
}

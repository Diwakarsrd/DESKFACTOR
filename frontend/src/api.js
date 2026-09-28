const BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function request(path, options) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, options);
  } catch {
    throw new Error("Cannot reach the server. Check your connection and try again.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || body.detail || `Request failed (${res.status}).`);
  return body;
}

export const submitText = (text) => {
  const f = new FormData();
  f.append("text", text);
  return request("/api/analyses", { method: "POST", body: f });
};
export const submitFile = (file) => {
  const f = new FormData();
  f.append("file", file);
  return request("/api/analyses", { method: "POST", body: f });
};
export const listAnalyses = () => request("/api/analyses");
export const getAnalysis = (id) => request(`/api/analyses/${id}`);

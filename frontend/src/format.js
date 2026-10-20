export const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString() : "—");
export const fmtBytes = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
export const fmtSecs = (s) => (s == null ? "—" : s >= 60 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : `${s.toFixed(1)} s`);
export const num = (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d));

export const VERDICT = {
  real_like: { label: "Real-like", cls: "real" },
  fake_like: { label: "Fake-like", cls: "fake" },
  inconclusive: { label: "Inconclusive", cls: "inc" },
};
export function statusInfo(a) {
  if (a.status === "failed") return { label: "Failed", cls: "failed" };
  if (a.status === "queued" || a.status === "processing") return { label: "Processing", cls: "proc" };
  return VERDICT[a.verdict] || { label: "—", cls: "inc" };
}
export const REGION = { forehead: "Forehead", left_cheek: "Left cheek", right_cheek: "Right cheek" };

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { fmtDate, fmtSecs } from "../format.js";
import Badge from "../components/Badge.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";

const QUALITY = { good: "Good", marginal: "Marginal", insufficient: "Insufficient" };

export default function History() {
  const [q, setQ] = useState({ search: "", verdict: "all", sort: "newest", page: 1 });
  const [text, setText] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [toDelete, setToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {                       // debounce the search box
    const t = setTimeout(() => setQ((p) => ({ ...p, search: text.trim(), page: 1 })), 300);
    return () => clearTimeout(t);
  }, [text]);

  const load = () => api.list({ ...q, page_size: 10 }).then((d) => { setData(d); setError(""); }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [q]);
  useEffect(() => {                       // refresh while something is still being analysed
    if (!data?.items.some((a) => a.status === "queued" || a.status === "processing")) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [data]);

  async function confirmDelete() {
    setDeleting(true);
    try {
      await api.remove(toDelete.id);
      setToDelete(null);
      await load();
    } catch (e) { if (e.status === 404) { setToDelete(null); load(); } else setError(e.message); }
    setDeleting(false);
  }

  const set = (patch) => setQ((p) => ({ ...p, ...patch, page: patch.page ?? 1 }));
  const filtered = q.search || q.verdict !== "all";

  return (
    <div className="card">
      <h1>Previous analyses</h1>
      <div className="row filters">
        <input type="search" placeholder="Search by file name" value={text} onChange={(e) => setText(e.target.value)} />
        <select value={q.verdict} onChange={(e) => set({ verdict: e.target.value })}>
          <option value="all">All results</option><option value="real_like">Real-like</option>
          <option value="fake_like">Fake-like</option><option value="inconclusive">Inconclusive</option>
          <option value="failed">Failed</option>
        </select>
        <select value={q.sort} onChange={(e) => set({ sort: e.target.value })}>
          <option value="newest">Newest first</option><option value="oldest">Oldest first</option>
        </select>
      </div>
      {error && <div className="alert error">{error}</div>}

      {data && data.items.length === 0 && (
        <p className="empty">{filtered ? "No analyses match these filters." : <>No analyses yet. <Link to="/upload">Analyze a video</Link> and it will appear here.</>}</p>
      )}
      {data && data.items.length > 0 && (
        <div className="scroll">
          <table>
            <thead><tr><th>Video</th><th>Date</th><th>Result</th><th>Signal quality</th><th>Time</th><th /></tr></thead>
            <tbody>
              {data.items.map((a) => (
                <tr key={a.id}>
                  <td className="name">{a.file_name}</td>
                  <td>{fmtDate(a.created_at)}</td>
                  <td><Badge analysis={a} /></td>
                  <td>{a.status === "completed" ? QUALITY[a.signal_quality] || "—" : a.stage || "—"}</td>
                  <td>{fmtSecs(a.processing_seconds)}</td>
                  <td className="actions">
                    <Link className="btn ghost small" to={`/analyses/${a.id}`}>View report</Link>
                    <button className="btn danger-ghost small" onClick={() => setToDelete(a)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && data.pages > 1 && (
        <div className="row between pager">
          <button className="btn ghost small" disabled={q.page <= 1} onClick={() => set({ page: q.page - 1 })}>← Previous</button>
          <span className="muted">Page {data.page} of {data.pages} · {data.total} analyses</span>
          <button className="btn ghost small" disabled={q.page >= data.pages} onClick={() => set({ page: q.page + 1 })}>Next →</button>
        </div>
      )}
      {toDelete && (
        <ConfirmDialog title="Delete this analysis?" busy={deleting} onConfirm={confirmDelete} onCancel={() => setToDelete(null)}>
          “{toDelete.file_name}” and its saved report will be permanently removed. This cannot be undone.
        </ConfirmDialog>
      )}
    </div>
  );
}

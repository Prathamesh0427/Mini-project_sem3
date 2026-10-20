import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { fmtDate } from "../format.js";
import Badge from "../components/Badge.jsx";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.stats(), api.list({ page_size: 5 })])
      .then(([s, l]) => { setStats(s); setRecent(l.items); })
      .catch((e) => setError(e.message));
  }, []);

  const tiles = stats && [
    ["Videos analyzed", stats.analyzed], ["Real-like", stats.real_like],
    ["Fake-like", stats.fake_like], ["Inconclusive", stats.inconclusive],
  ];

  return (
    <>
      <section className="hero">
        <svg className="ecg" viewBox="0 0 600 60" preserveAspectRatio="none" aria-hidden="true">
          <polyline fill="none" strokeWidth="2" points="0,34 120,34 140,34 150,12 160,52 172,34 300,34 320,34 330,14 340,50 352,34 480,34 500,34 510,10 520,54 532,34 600,34" />
        </svg>
        <h1>rPPG-Based Explainable Deepfake Detection</h1>
        <p>
          A beating heart makes skin colour change very slightly with every pulse. This tool measures that
          faint signal on the forehead and both cheeks, then checks whether the three regions agree with each
          other. It reports what it measured and why — and says “inconclusive” when the video is not good enough.
        </p>
        <Link className="btn primary big" to="/upload">Analyze a new video</Link>
      </section>

      {error && <div className="alert error">{error}</div>}
      {tiles && (
        <section className="tiles">
          {tiles.map(([label, value]) => <div className="tile" key={label}><b>{value}</b><span>{label}</span></div>)}
        </section>
      )}
      {stats && <p className="note">These counts only summarise the results saved in this app. They are not a measure of the detector’s accuracy.
        {stats.failed > 0 && ` (${stats.failed} analysis ${stats.failed === 1 ? "run" : "runs"} failed and ${stats.failed === 1 ? "is" : "are"} not counted above.)`}</p>}

      <section className="card">
        <div className="row between"><h2>Recent analyses</h2><Link to="/history">View all history →</Link></div>
        {stats && recent.length === 0 && <p className="empty">No analyses yet. <Link to="/upload">Analyze your first video.</Link></p>}
        <ul className="list">
          {recent.map((a) => (
            <li key={a.id}>
              <Link to={`/analyses/${a.id}`}>{a.file_name}</Link>
              <span className="muted">{fmtDate(a.created_at)}</span>
              <Badge analysis={a} />
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

import { NavLink, Route, Routes, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard.jsx";
import Upload from "./pages/Upload.jsx";
import Report from "./pages/Report.jsx";
import History from "./pages/History.jsx";

export default function App() {
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand"><span className="beat">♥</span> rPPG Deepfake Detection</Link>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/upload">Analyze video</NavLink>
          <NavLink to="/history">History</NavLink>
        </nav>
      </header>
      <main className="page">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/history" element={<History />} />
          <Route path="/analyses/:id" element={<Report />} />
          <Route path="*" element={<div className="card"><h2>Page not found</h2><Link to="/">Back to the dashboard</Link></div>} />
        </Routes>
      </main>
    </>
  );
}

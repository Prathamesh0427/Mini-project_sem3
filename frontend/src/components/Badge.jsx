import { statusInfo } from "../format.js";

export default function Badge({ analysis }) {
  const s = statusInfo(analysis);
  return <span className={`badge ${s.cls}`}>{s.label}</span>;
}

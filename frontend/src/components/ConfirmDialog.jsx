export default function ConfirmDialog({ title, children, confirmLabel = "Delete", busy, onConfirm, onCancel }) {
  return (
    <div className="overlay" role="dialog" aria-modal="true" onClick={onCancel}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <p>{children}</p>
        <div className="row end">
          <button className="btn ghost" onClick={onCancel} disabled={busy}>Cancel</button>
          <button className="btn danger" onClick={onConfirm} disabled={busy}>{busy ? "Deleting…" : confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

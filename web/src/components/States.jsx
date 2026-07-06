import React from 'react'

export function Spinner({ label = 'Loading' }) {
  return <span className="spinner" role="status"><span />{label}</span>
}

export function PageSkeleton({ rows = 3 }) {
  return (
    <div className="page-state" aria-label="Loading page" aria-busy="true">
      <div className="skeleton sk-title" />
      <div className="skeleton sk-sub" />
      <div className="skeleton-grid">
        {Array.from({ length: rows }, (_, i) => <div className="skeleton sk-card" key={i} />)}
      </div>
    </div>
  )
}

export function EmptyState({ eyebrow = 'Nothing here yet', title, body, action }) {
  return (
    <div className="empty-state">
      <div className="empty-glyph" aria-hidden="true">○</div>
      <div className="eyebrow">{eyebrow}</div>
      <h2>{title}</h2>
      {body && <p>{body}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ error, retry }) {
  return (
    <div className="error-state" role="alert">
      <div>
        <div className="eyebrow">Unable to load</div>
        <strong>{error?.message ?? 'Something went wrong.'}</strong>
        <p>The service did not return this workspace. Your current view is safe.</p>
      </div>
      {retry && <button className="btn ghost" onClick={retry}>Try again</button>}
    </div>
  )
}

export function PermissionHint({ children }) {
  return <div className="permission-hint" role="note">{children}</div>
}


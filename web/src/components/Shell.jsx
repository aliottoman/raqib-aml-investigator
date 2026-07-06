import React, { useEffect, useRef, useState } from 'react'
import { ROLES } from '../api.js'
import { Link } from '../router.jsx'

const NAV = [
  ['overview', 'Overview', 'M4 5h7v7H4zM13 5h7v4h-7zM13 11h7v8h-7zM4 14h7v5H4z'],
  ['alerts', 'Alerts', 'M12 3 3.5 18h17L12 3Zm0 5v5m0 3v.2'],
  ['cases', 'Cases', 'M4 7h16v12H4zM8 7V5h8v2'],
  ['intelligence', 'Intelligence', 'M4 18V9m5 9V5m5 13v-6m5 6V3'],
  ['architecture', 'Architecture', 'M5 6h14v5H5zM3 15h6v5H3zm12 0h6v5h-6zM12 11v4M6 15v-2h12v2'],
]

function NavIcon({ path }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={path} /></svg>
}

function PersonaSwitcher({ role, onRoleChange }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const close = (event) => { if (!ref.current?.contains(event.target)) setOpen(false) }
    const escape = (event) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [])
  const active = ROLES[role]
  return (
    <div className="persona" ref={ref}>
      <button className="persona-trigger" onClick={() => setOpen((v) => !v)} aria-haspopup="listbox" aria-expanded={open}>
        <span className="avatar">{active.initials}</span>
        <span className="persona-copy"><small>Viewing as</small><strong>{active.short}</strong></span>
        <span className="chevron" aria-hidden="true">⌄</span>
      </button>
      {open && (
        <div className="persona-menu" role="listbox" aria-label="Demo persona">
          <div className="persona-note"><span>Simulation</span> Switch roles to preview governed workflows.</div>
          {Object.entries(ROLES).map(([key, item]) => (
            <button
              key={key}
              role="option"
              aria-selected={role === key}
              className={role === key ? 'selected' : ''}
              onClick={() => { onRoleChange(key); setOpen(false) }}
            >
              <span className="avatar mini">{item.initials}</span>
              <span><strong>{item.label}</strong><small>{item.description}</small></span>
              {role === key && <span className="check">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Shell({ path, role, setRole, health, children }) {
  const active = path.startsWith('/cases/') ? 'cases' : path.split('/')[1] || 'overview'
  const currentLabel = NAV.find(([key]) => key === active)?.[1] ?? 'Workspace'
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link to="/overview" className="wordmark" aria-label="Raqib home">
          <span className="brand-seal"><img src="/brand/raqib-mark.svg" alt="" /></span>
          <span><strong>Raqib</strong><small>رقيب</small></span>
        </Link>
        <nav aria-label="Primary navigation">
          {NAV.map(([key, label, icon]) => (
            <Link key={key} to={`/${key}`} className={active === key ? 'active' : ''} aria-current={active === key ? 'page' : undefined}>
              <NavIcon path={icon} /><span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className={`service-dot ${health?.live_available ? 'live' : ''}`} />
          <span><strong>{health?.live_available ? 'OCI live' : 'Recorded mode'}</strong><small>Technical reference</small></span>
        </div>
      </aside>

      <div className="shell-body">
        <header className="appbar">
          <div className="mobile-brand"><span className="brand-seal"><img src="/brand/raqib-mark.svg" alt="" /></span><strong>Raqib</strong></div>
          <div className="location"><span>Financial Crime Operations</span><strong>{currentLabel}</strong></div>
          <div className="appbar-actions">
            <span className="demo-badge">Synthetic data</span>
            <PersonaSwitcher role={role} onRoleChange={setRole} />
          </div>
        </header>
        <main className="workspace" id="main-content">{children}</main>
        <footer>Fictional institution and synthetic data · Technical reference on Oracle Cloud Infrastructure</footer>
      </div>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        {NAV.map(([key, label, icon]) => (
          <Link key={key} to={`/${key}`} className={active === key ? 'active' : ''} aria-label={label}>
            <NavIcon path={icon} /><span>{label === 'Intelligence' ? 'Intel' : label}</span>
          </Link>
        ))}
      </nav>
    </div>
  )
}

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { EmptyState, ErrorState, PageSkeleton } from '../components/States.jsx'
import { navigate } from '../router.jsx'

const STATUSES = ['all', 'open', 'investigating', 'draft_ready', 'pending_review', 'changes_requested', 'approved', 'closed']

function normaliseCase(item) {
  return {
    id: item.id ?? item.case_id ?? item.alert_id,
    subject: item.subject ?? item.customer_name ?? item.customer?.name ?? 'Unknown subject',
    status: item.case_status ?? item.status ?? 'open',
    severity: item.severity ?? item.risk_level ?? 'medium',
    rule: item.rule ?? item.alert?.rule ?? '—',
    owner: item.owner ?? item.assigned_to ?? 'Unassigned',
    updated: item.updated_at ?? item.updated ?? item.created ?? '',
    summary: item.summary ?? item.alert?.summary ?? '',
  }
}

export default function CasesPage({ role }) {
  const [cases, setCases] = useState(null)
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const load = useCallback(() => {
    setError(null)
    api('/api/cases', { role })
      .catch(() => api('/api/alerts', { role }))
      .then((d) => setCases((d.cases ?? d.alerts ?? d ?? []).map(normaliseCase)))
      .catch(setError)
  }, [role])
  useEffect(load, [load])

  const view = useMemo(() => (cases ?? []).filter((item) => {
    const statusMatch = status === 'all' || item.status === status || (status === 'closed' && item.status.startsWith('closed'))
    return statusMatch && `${item.id} ${item.subject} ${item.rule} ${item.owner}`.toLowerCase().includes(query.toLowerCase())
  }), [cases, query, status])
  if (error) return <ErrorState error={error} retry={load} />
  if (!cases) return <PageSkeleton rows={4} />

  return (
    <div className="page cases-page">
      <header className="page-head">
        <div><div className="eyebrow">Investigation workbench</div><h1>Cases</h1><p>Evidence, decisions, and reports in one governed record.</p></div>
        <div className="head-stat"><strong>{cases.filter((item) => !item.status.startsWith('closed')).length}</strong><span>active cases</span></div>
      </header>
      <section className="surface queue-surface">
        <div className="toolbar">
          <label className="search-field"><span aria-hidden="true">⌕</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search cases" aria-label="Search cases" /></label>
          <div className="filter-tabs status-tabs" role="group" aria-label="Filter by case status">
            {STATUSES.map((item) => <button key={item} className={status === item ? 'active' : ''} onClick={() => setStatus(item)}>{item.replace('_', ' ')}</button>)}
          </div>
        </div>
        {view.length ? (
          <div className="case-cards">
            {view.map((item) => (
              <button key={item.id} className="case-card" onClick={() => navigate(`/cases/${item.id}`)}>
                <div className="case-card-top"><span className={`severity-label ${item.severity}`}><i />{item.severity}</span><span className={`status-label ${item.status}`}>{item.status.replaceAll('_', ' ')}</span></div>
                <div><small>{item.id}</small><h3>{item.subject}</h3><p>{item.summary}</p></div>
                <dl><div><dt>Trigger</dt><dd>{item.rule}</dd></div><div><dt>Owner</dt><dd>{item.owner}</dd></div><div><dt>Updated</dt><dd>{String(item.updated).slice(0, 10) || '—'}</dd></div></dl>
                <span className="text-link">Open workspace →</span>
              </button>
            ))}
          </div>
        ) : <EmptyState title="No cases match this view" body="Try another status or clear your search." />}
      </section>
    </div>
  )
}

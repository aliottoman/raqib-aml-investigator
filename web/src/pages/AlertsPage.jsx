import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, can } from '../api.js'
import { EmptyState, ErrorState, PageSkeleton, PermissionHint, Spinner } from '../components/States.jsx'
import { navigate } from '../router.jsx'

const FILTERS = ['all', 'critical', 'high', 'medium', 'low']
const PRIORITIES = ['urgent', 'high', 'medium', 'low']
const CASE_STATUSES = [
  ['open', 'Open'],
  ['investigating', 'Investigating'],
  ['draft_ready', 'Draft ready'],
  ['pending_review', 'Pending review'],
  ['changes_requested', 'Changes requested'],
  ['approved', 'Approved'],
  ['closed', 'Closed'],
]

const caseStatus = (item) => item.workflow_status ?? item.case_status ?? item.status ?? 'open'
const caseStatusLabel = (value) => CASE_STATUSES.find(([status]) => status === value)?.[1]
  ?? String(value).replaceAll('_', ' ')

export default function AlertsPage({ role }) {
  const [alerts, setAlerts] = useState(null)
  const [triage, setTriage] = useState(null)
  const [filter, setFilter] = useState('all')
  const [status, setStatus] = useState('open')
  const [rule, setRule] = useState('all')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(() => new Set())
  const [owner, setOwner] = useState('')
  const [priority, setPriority] = useState('high')
  const [reason, setReason] = useState('')
  const [reviewingClose, setReviewingClose] = useState(false)
  const [busy, setBusy] = useState(false)
  const [screening, setScreening] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [notice, setNotice] = useState(null)
  const [queueError, setQueueError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const timeout = useRef(null)
  const reviewCloseButton = useRef(null)
  const confirmCloseButton = useRef(null)
  const canTriage = can(role, 'transition')

  const load = useCallback(() => {
    setQueueError(null)
    api('/api/alerts', { role }).then((d) => setAlerts(d.alerts ?? d ?? [])).catch(setQueueError)
    api('/api/triage', { role }).then(setTriage).catch(() => setTriage(null))
  }, [role])
  useEffect(load, [load])
  useEffect(() => () => clearTimeout(timeout.current), [])
  useEffect(() => {
    if (reviewingClose) confirmCloseButton.current?.focus()
  }, [reviewingClose])

  const flash = (summary, { tone = 'success', skipped = [] } = {}) => {
    clearTimeout(timeout.current)
    setNotice({ summary, tone, skipped })
    timeout.current = setTimeout(() => setNotice(null), skipped.length ? 12000 : 7000)
  }

  const runScreening = async () => {
    setScreening(true)
    setNotice(null)
    setActionError(null)
    try {
      const result = await api('/api/screening/run', { method: 'POST', role })
      setSelected(new Set())
      load()
      flash(`${result.transactions_scanned?.toLocaleString() ?? 'All'} transactions evaluated · ${(result.alerts ?? []).length} signals raised`)
    } catch (e) { setActionError(e) } finally { setScreening(false) }
  }

  const resetDemo = async () => {
    setResetting(true)
    setNotice(null)
    setActionError(null)
    try {
      const result = await api('/api/demo/reset', { method: 'POST', role })
      setSelected(new Set())
      load()
      const n = result.reopened_count ?? 0
      flash(
        n
          ? `Demo reset · ${n} ${n === 1 ? 'case' : 'cases'} reopened to the active queue.`
          : 'Demo reset · the queue was already at its initial state.',
        { tone: n ? 'success' : 'neutral' },
      )
    } catch (e) { setActionError(e) } finally { setResetting(false) }
  }

  const rules = useMemo(() => [...new Set((alerts ?? []).map((a) => a.rule))].sort(), [alerts])
  const filtered = useMemo(() => (alerts ?? []).filter((item) => {
    const matchSeverity = filter === 'all' || item.severity === filter
    const matchStatus = status === 'all' || caseStatus(item) === status
    const matchRule = rule === 'all' || item.rule === rule
    const haystack = `${item.id} ${item.customer_name} ${item.rule} ${item.summary} ${item.owner ?? ''} ${item.priority ?? ''}`.toLowerCase()
    return matchSeverity && matchStatus && matchRule && haystack.includes(query.toLowerCase())
  }), [alerts, filter, status, rule, query])

  const visibleIds = useMemo(() => filtered.map((a) => a.id), [filtered])
  const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selected.has(id))
  const toggle = (id) => {
    setReviewingClose(false)
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }
  const toggleAll = () => {
    setReviewingClose(false)
    setSelected((prev) => {
      if (allSelected) return new Set([...prev].filter((id) => !visibleIds.includes(id)))
      return new Set([...prev, ...visibleIds])
    })
  }

  const clearSelectionForViewChange = () => {
    if (!selected.size) return
    setSelected(new Set())
    setReviewingClose(false)
    flash('Selection cleared because the queue view changed.', { tone: 'neutral' })
  }

  const cancelCloseReview = () => {
    setReviewingClose(false)
    reviewCloseButton.current?.focus()
  }

  const runBulk = async (action, extra) => {
    setBusy(true)
    setNotice(null)
    setActionError(null)
    try {
      const result = await api('/api/cases/bulk', {
        method: 'POST', role, body: { case_ids: [...selected], action, ...extra },
      })
      const updatedCount = result.updated_count ?? result.updated?.length ?? 0
      const skipped = result.skipped ?? []
      const skippedCount = result.skipped_count ?? skipped.length
      const noun = updatedCount === 1 ? 'case' : 'cases'
      const actionSummary = action === 'assign'
        ? `${updatedCount} ${noun} assigned to ${extra.owner.trim()}.`
        : action === 'priority'
          ? `${updatedCount} ${noun} set to ${extra.priority} priority.`
          : `${updatedCount} ${noun} closed with a recorded rationale.`
      const knownIds = new Set((alerts ?? []).map((item) => item.id))
      setSelected(new Set(skipped.map((item) => item.case_id).filter((id) => knownIds.has(id))))
      setReviewingClose(false)
      if (action === 'assign') setOwner('')
      if (action === 'transition') setReason('')
      load()
      flash(actionSummary + (skippedCount ? ` ${skippedCount} could not be updated; review the details below.` : ''), {
        tone: skippedCount ? 'warning' : 'success',
        skipped,
      })
    } catch (e) { setActionError(e) } finally { setBusy(false) }
  }

  if (queueError && !alerts) return <ErrorState error={queueError} retry={load} />
  if (!alerts) return <PageSkeleton rows={4} />
  const screenAllowed = can(role, 'screen')
  const resetAllowed = can(role, 'reset_demo')
  const selectedCount = selected.size

  return (
    <div className="page alerts-page">
      <header className="page-head">
        <div><div className="eyebrow">Deterministic monitoring</div><h1>Alert queue</h1><p>Prioritized signals generated by explainable detection rules.</p></div>
        <div className="head-actions">
          {resetAllowed && (
            <button className="btn ghost" onClick={resetDemo} disabled={resetting || screening}
              title="Reopen resolved cases so the critical and high signals return to the queue">
              {resetting ? <Spinner label="Resetting" /> : 'Reset demo'}
            </button>
          )}
          <button className="btn primary" onClick={runScreening} disabled={screening || resetting || !screenAllowed} title={!screenAllowed ? 'Available to the AML Analyst persona' : undefined}>
            {screening ? <Spinner label="Screening" /> : 'Run screening'}
          </button>
        </div>
      </header>
      {!screenAllowed && <PermissionHint>Screening is analyst-controlled. Switch to the <strong>AML Analyst</strong> persona to run the rule set.</PermissionHint>}
      {queueError && (
        <div className="queue-notice error" role="alert">
          <div><strong>Queue refresh failed</strong><span>{queueError.message ?? 'The latest queue could not be loaded.'}</span></div>
          <button className="btn ghost" onClick={load}>Try again</button>
        </div>
      )}
      {actionError && (
        <div className="queue-notice error" role="alert">
          <div><strong>Action not completed</strong><span>{actionError.message ?? 'The requested update could not be completed.'}</span></div>
          <button className="icon-button" onClick={() => setActionError(null)} aria-label="Dismiss action error">×</button>
        </div>
      )}
      {notice && (
        <div className={`queue-notice ${notice.tone}`} role={notice.tone === 'warning' ? 'alert' : 'status'}>
          <div>
            <strong>{notice.summary}</strong>
            {notice.skipped.length > 0 && (
              <ul>{notice.skipped.map((item) => <li key={item.case_id}><span className="mono">{item.case_id}</span> — {item.reason}</li>)}</ul>
            )}
          </div>
          <button className="icon-button" onClick={() => setNotice(null)} aria-label="Dismiss queue notice">×</button>
        </div>
      )}

      {triage && (
        <div className="triage-strip" aria-label="Queue summary">
          <span><strong>{triage.active}</strong> active</span>
          <span><strong>{triage.unassigned}</strong> unassigned</span>
          {FILTERS.slice(1).map((sev) => (triage.by_severity?.[sev] ? (
            <span key={sev} className={`triage-sev ${sev}`}><i />{triage.by_severity[sev]} {sev}</span>
          ) : null))}
        </div>
      )}

      <section className="surface queue-surface">
        <div className="toolbar">
          <label className="search-field"><span aria-hidden="true">⌕</span><input value={query} onChange={(e) => { clearSelectionForViewChange(); setQuery(e.target.value) }} placeholder="Search customer, alert, rule, owner, or priority" aria-label="Search alerts" /></label>
          <div className="filter-tabs" role="group" aria-label="Filter by severity">
            {FILTERS.map((item) => <button key={item} className={filter === item ? 'active' : ''} aria-pressed={filter === item} onClick={() => { clearSelectionForViewChange(); setFilter(item) }}>{item}</button>)}
          </div>
          <label className="select-field"><span>Rule</span><select value={rule} onChange={(e) => { clearSelectionForViewChange(); setRule(e.target.value) }}><option value="all">All rules</option>{rules.map((r) => <option key={r} value={r}>{r}</option>)}</select></label>
          <label className="select-field"><span>Status</span><select value={status} onChange={(e) => { clearSelectionForViewChange(); setStatus(e.target.value) }}><option value="all">All</option>{CASE_STATUSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        </div>

        {canTriage && selectedCount > 0 && (
          <div className="bulk-bar" role="region" aria-label="Bulk triage actions">
            <span className="bulk-count"><strong>{selectedCount}</strong> selected</span>
            <span className="bulk-group">
              <input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="Assign owner…" aria-label="Owner" />
              <button className="btn ghost" disabled={busy || !owner.trim()} onClick={() => runBulk('assign', { owner })}>Assign</button>
            </span>
            <span className="bulk-group">
              <select value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Priority">{PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}</select>
              <button className="btn ghost" disabled={busy} onClick={() => runBulk('priority', { priority })}>Set priority</button>
            </span>
            <span className="bulk-group">
              <input value={reason} maxLength={500} onChange={(e) => { setReason(e.target.value); setReviewingClose(false) }} placeholder="Close rationale…" aria-label="Close rationale" />
              <button ref={reviewCloseButton} className="btn crimson-o" disabled={busy || !reason.trim()} onClick={() => setReviewingClose(true)}>Review close</button>
            </span>
            <button className="btn ghost bulk-clear" onClick={() => { setSelected(new Set()); setReviewingClose(false) }}>Clear</button>
            {reviewingClose && (
              <div className="close-review" role="region" aria-labelledby="close-review-title" onKeyDown={(event) => { if (event.key === 'Escape') cancelCloseReview() }}>
                <div>
                  <strong id="close-review-title">Confirm closing {selectedCount} {selectedCount === 1 ? 'case' : 'cases'}</strong>
                  <p>This removes the selected cases from the active queue. The rationale is retained in each case audit trail.</p>
                </div>
                <dl>
                  <div><dt>Cases</dt><dd>{[...selected].join(', ')}</dd></div>
                  <div><dt>Rationale</dt><dd>{reason.trim()}</dd></div>
                </dl>
                <div className="close-review-actions">
                  <button className="btn ghost" onClick={cancelCloseReview}>Go back</button>
                  <button ref={confirmCloseButton} className="btn danger" disabled={busy} onClick={() => runBulk('transition', { status: 'closed', reason: reason.trim() })}>
                    {busy ? <Spinner label="Closing" /> : 'Confirm close'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {filtered.length ? (
          <div className={`data-table alert-table ${canTriage ? 'selectable' : ''}`} role="table" aria-label="Alerts">
            <div role="rowgroup">
              <div className="table-head" role="row">
                {canTriage && <span role="columnheader"><input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all in view" /></span>}
                <span role="columnheader">Severity</span><span role="columnheader">Customer & signal</span><span role="columnheader">Owner & priority</span><span role="columnheader">Rule</span><span role="columnheader">Raised</span><span role="columnheader">Status</span><span role="columnheader"><span className="sr-only">Open case</span></span>
              </div>
            </div>
            <div role="rowgroup">
              {filtered.map((alert) => (
                <div className={`table-row ${selected.has(alert.id) ? 'selected' : ''}`} key={alert.id} role="row">
                  {canTriage && (
                    <span className="row-check" role="cell">
                      <input type="checkbox" checked={selected.has(alert.id)} aria-label={`Select ${alert.id}`} onChange={() => toggle(alert.id)} />
                    </span>
                  )}
                  <span className="col-severity" role="cell"><span className={`severity-label ${alert.severity}`}><i />{alert.severity}</span></span>
                  <span className="col-signal" role="cell"><strong>{alert.customer_name}</strong><small>{alert.id} · {alert.summary}</small></span>
                  <span className="col-triage" role="cell">
                    <span className={`priority-label ${alert.priority ?? 'medium'}`}>{alert.priority ?? 'medium'}</span>
                    <small>{alert.owner || 'Unassigned'}</small>
                  </span>
                  <span className="mono col-rule" role="cell">{alert.rule}</span>
                  <span className="col-raised" role="cell">{String(alert.created ?? '—').slice(0, 10)}</span>
                  <span className="col-status" role="cell"><span className={`status-label ${caseStatus(alert)}`}>{caseStatusLabel(caseStatus(alert))}</span></span>
                  <span className="row-action" role="cell">
                    <button className="row-open" onClick={() => navigate(`/cases/${alert.id}`)} aria-label={`Open case ${alert.id}`}>→</button>
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <EmptyState title="No alerts match this view" body="Adjust the severity, status, rule, or search filters to widen the queue." />
        )}
      </section>
    </div>
  )
}

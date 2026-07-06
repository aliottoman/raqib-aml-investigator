import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { ErrorState, PageSkeleton } from '../components/States.jsx'
import { Link, navigate } from '../router.jsx'

function Metric({ label, value, detail, tone }) {
  return (
    <div className="metric">
      <div className="metric-top"><span>{label}</span>{tone && <i className={tone} />}</div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  )
}

function SeverityBar({ label, count, total, tone }) {
  const width = total ? Math.max(6, Math.round((count / total) * 100)) : 0
  return (
    <div className="severity-row">
      <span>{label}</span><div className="severity-track"><i className={tone} style={{ width: `${width}%` }} /></div><strong>{count}</strong>
    </div>
  )
}

export default function OverviewPage({ role }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const load = useCallback(() => {
    setError(null)
    Promise.all([
      api('/api/overview', { role }).catch(() => null),
      api('/api/alerts', { role }),
      api('/api/portfolio', { role }),
    ]).then(([overview, alerts, portfolio]) => {
      setData({ overview: overview ?? {}, alerts: alerts.alerts ?? alerts ?? [], customers: portfolio.customers ?? portfolio ?? [] })
    }).catch(setError)
  }, [role])
  useEffect(load, [load])

  const view = useMemo(() => {
    if (!data) return null
    const o = data.overview
    const metrics = o.metrics ?? {}
    const alerts = data.alerts
    const counts = o.severity_counts ?? alerts.reduce((acc, item) => {
      acc[item.severity] = (acc[item.severity] ?? 0) + 1
      return acc
    }, {})
    const open = alerts.filter((item) => (item.status ?? 'open') === 'open')
    return {
      open: o.open_alerts ?? open.length,
      activeCases: metrics.active_cases ?? o.active_cases ?? open.length,
      pendingReview: metrics.pending_review ?? o.pending_review ?? alerts.filter((item) => ['submitted', 'pending_review'].includes(item.status)).length,
      counts,
      priority: o.priority_alert ?? o.priority_queue?.[0] ?? open[0] ?? alerts[0],
      recent: o.recent_alerts ?? o.recent_cases ?? alerts.slice(0, 5),
      customers: metrics.coverage?.customers ?? o.customers_monitored ?? data.customers.length,
      coverage: typeof metrics.coverage === 'string' ? metrics.coverage : `${o.rules_active ?? 4} deterministic rules`,
    }
  }, [data])

  if (error) return <ErrorState error={error} retry={load} />
  if (!view) return <PageSkeleton rows={4} />
  const total = Object.values(view.counts).reduce((sum, n) => sum + Number(n), 0)

  return (
    <div className="page overview-page">
      <header className="page-head hero-head">
        <div>
          <div className="eyebrow">Operations overview · today</div>
          <h1>Good morning. Your queue is under control.</h1>
          <p>{view.open} alerts require attention across {view.customers} monitored customers.</p>
        </div>
        {view.priority && <button className="btn primary" onClick={() => navigate(`/cases/${view.priority.id}`)}>Review priority case</button>}
      </header>

      <section className="metric-strip" aria-label="Operational metrics">
        <Metric label="Open alerts" value={view.open} detail="Awaiting triage" tone="critical" />
        <Metric label="Active cases" value={view.activeCases} detail="In investigation" tone="medium" />
        <Metric label="Pending review" value={view.pendingReview} detail="MLRO decisions" tone="high" />
        <Metric label="Monitoring coverage" value={view.coverage} detail={`${view.customers} synthetic customers`} tone="clear" />
      </section>

      <div className="overview-grid">
        <section className="surface priority-card">
          <div className="section-head">
            <div><div className="eyebrow">Next best action</div><h2>Priority case</h2></div>
            <Link to="/alerts" className="text-link">View queue</Link>
          </div>
          {view.priority ? (
            <button className="priority-case" onClick={() => navigate(`/cases/${view.priority.id}`)}>
              <div className="priority-mark"><span>{String(view.priority.severity ?? 'high').slice(0, 1).toUpperCase()}</span></div>
              <div>
                <div className="row-title">{view.priority.customer_name ?? view.priority.subject ?? view.priority.title ?? 'Customer review'}</div>
                <div className="row-meta">{view.priority.id} · {String(view.priority.rule ?? 'Investigation').replaceAll('_', ' ')}</div>
                <p>{view.priority.summary}</p>
              </div>
              <span className="round-arrow" aria-hidden="true">→</span>
            </button>
          ) : <p className="muted">No priority case is waiting.</p>}
        </section>

        <section className="surface risk-panel">
          <div className="section-head"><div><div className="eyebrow">Queue health</div><h2>Alerts by severity</h2></div><span className="large-total">{total}</span></div>
          <div className="severity-bars">
            <SeverityBar label="Critical" count={view.counts.critical ?? 0} total={total} tone="critical" />
            <SeverityBar label="High" count={view.counts.high ?? 0} total={total} tone="high" />
            <SeverityBar label="Medium" count={view.counts.medium ?? 0} total={total} tone="medium" />
            <SeverityBar label="Low" count={view.counts.low ?? 0} total={total} tone="low" />
          </div>
        </section>

        <section className="surface recent-panel">
          <div className="section-head"><div><div className="eyebrow">Latest signals</div><h2>Recent alerts</h2></div><Link to="/alerts" className="text-link">All alerts</Link></div>
          <div className="compact-list">
            {view.recent.map((alert) => (
              <button key={alert.id} onClick={() => navigate(`/cases/${alert.id}`)}>
                <span className={`status-beacon ${alert.severity}`} />
                <span><strong>{alert.customer_name ?? alert.title}</strong><small>{alert.id} · {alert.rule}</small></span>
                <span className={`chip ${alert.severity}`}>{alert.severity}</span>
                <span className="row-date">{String(alert.created ?? '').slice(0, 10)}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="surface principles-panel">
          <div className="eyebrow">Operating model</div>
          <blockquote>Rules detect.<br />AI investigates.<br /><em>Humans decide.</em></blockquote>
          <p>Every recommendation remains evidence-linked, policy-grounded, and under explicit analyst control.</p>
          <Link to="/architecture" className="text-link">Explore the architecture →</Link>
        </section>
      </div>
    </div>
  )
}

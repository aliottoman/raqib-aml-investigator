import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api, can } from '../api.js'
import { EmptyState, ErrorState, PageSkeleton, PermissionHint, Spinner } from '../components/States.jsx'

const FALLBACK_RULES = [
  { id: 'CASH-VELOCITY-04', name: 'Sub-threshold cash velocity', description: 'Detects repeated cash deposits below the reporting threshold across a rolling business-day window.', category: 'Structuring', severity: 'critical', enabled: true, parameters: { minimum_deposits: 3, window_business_days: 10, threshold_aed: 37500, minimum_branches: 3 }, policy_reference: '§4.2' },
  { id: 'WATCHLIST-PROX-01', name: 'Watchlist proximity', description: 'Finds direct and related-party transfers involving governed watchlist records.', category: 'Sanctions & watchlists', severity: 'high', enabled: true, parameters: { minimum_match_score: 85 }, policy_reference: '§6.1' },
  { id: 'PROFILE-DEVIATION-02', name: 'Profile deviation', description: 'Flags sustained credits materially above the declared customer profile.', category: 'Customer behaviour', severity: 'medium', enabled: true, parameters: { turnover_multiplier: 2, consecutive_months: 2 }, policy_reference: '§5.4' },
  { id: 'DORMANT-SPIKE-03', name: 'Dormant account spike', description: 'Detects outsized credits shortly after a prolonged period of inactivity.', category: 'Account behaviour', severity: 'low', enabled: true, parameters: { quiet_days: 60, credit_multiplier: 1.2, observation_days: 14 }, policy_reference: '§5.7' },
]

const number = (value) => Number(value ?? 0)

function LineChart({ points }) {
  const values = points.length ? points : [{ label: 'Jan', value: 8 }, { label: 'Feb', value: 12 }, { label: 'Mar', value: 10 }, { label: 'Apr', value: 16 }, { label: 'May', value: 14 }, { label: 'Jun', value: 21 }]
  const w = 720, h = 210, px = 24, py = 26
  const max = Math.max(...values.map((point) => number(point.value)), 1)
  const coords = values.map((point, index) => ({ x: px + (index * (w - px * 2)) / Math.max(values.length - 1, 1), y: h - py - (number(point.value) / max) * (h - py * 2), ...point }))
  const line = coords.map((point, i) => `${i ? 'L' : 'M'} ${point.x} ${point.y}`).join(' ')
  const area = `${line} L ${coords.at(-1).x} ${h - py} L ${coords[0].x} ${h - py} Z`
  return (
    <svg className="line-chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Alert volume trend">
      {[0, .25, .5, .75, 1].map((ratio) => <line key={ratio} x1={px} x2={w - px} y1={py + ratio * (h - py * 2)} y2={py + ratio * (h - py * 2)} className="grid-line" />)}
      <path d={area} className="chart-area" /><path d={line} className="chart-line" />
      {coords.map((point) => <g key={point.label}><circle cx={point.x} cy={point.y} r="4" /><text x={point.x} y={h - 5} textAnchor="middle">{point.label}</text><title>{point.label}: {point.value}</title></g>)}
    </svg>
  )
}

function Donut({ segments }) {
  const items = segments.length ? segments : [{ label: 'Escalated', value: 4, tone: 'critical' }, { label: 'Investigating', value: 7, tone: 'high' }, { label: 'Closed', value: 11, tone: 'clear' }]
  const total = items.reduce((sum, item) => sum + number(item.value), 0) || 1
  let offset = 0
  return (
    <div className="donut-wrap">
      <svg className="donut" viewBox="0 0 42 42" role="img" aria-label="Case outcomes">
        <circle cx="21" cy="21" r="15.915" className="donut-bg" />
        {items.map((item) => {
          const size = (number(item.value) / total) * 100
          const element = <circle key={item.label} cx="21" cy="21" r="15.915" className={item.tone ?? item.label.toLowerCase()} strokeDasharray={`${size} ${100 - size}`} strokeDashoffset={-offset} />
          offset += size
          return element
        })}
        <text x="21" y="20" textAnchor="middle">{total}</text><text x="21" y="24" textAnchor="middle">cases</text>
      </svg>
      <div className="donut-legend">{items.map((item) => <div key={item.label}><i className={item.tone ?? item.label.toLowerCase()} /><span>{item.label}</span><strong>{item.value}</strong></div>)}</div>
    </div>
  )
}

function Analytics({ data, period, setPeriod }) {
  const trend = data.alert_trend ?? data.monthly_alerts ?? data.monthly_activity ?? data.trend ?? []
  const points = trend.map((item) => ({ label: item.label ?? item.month ?? item.date, value: item.value ?? item.count ?? item.alerts ?? item.transaction_count }))
  const outcomesRaw = data.case_outcomes ?? data.cases_by_status ?? data.outcomes ?? []
  const outcomes = Array.isArray(outcomesRaw)
    ? outcomesRaw.map((item, i) => ({ label: item.label ?? item.status ?? item.outcome, value: item.value ?? item.count, tone: item.tone ?? ['critical', 'high', 'clear', 'medium'][i] }))
    : Object.entries(outcomesRaw).map(([label, value], i) => ({ label: label.replaceAll('_', ' '), value, tone: ['critical', 'high', 'clear', 'medium'][i] }))
  const rules = data.rule_performance ?? data.top_rules ?? data.alerts_by_rule ?? []
  const maxRule = Math.max(...rules.map((item) => number(item.alerts ?? item.count)), 1)
  const kpis = data.kpis ?? data.summary ?? data
  return (
    <div className="analytics-view">
      <div className="subpage-head"><div><div className="eyebrow">Operational intelligence</div><h2>Monitoring performance</h2></div><div className="segment-control" aria-label="Analytics period">{['30d', '90d', '180d'].map((value) => <button className={period === value ? 'active' : ''} key={value} onClick={() => setPeriod(value)}>{value}</button>)}</div></div>
      <div className="insight-strip">
        <div><span>Customers monitored</span><strong>{kpis.customers_monitored ?? '—'}</strong><small>synthetic customer book</small></div>
        <div><span>Transactions observed</span><strong>{number(kpis.transactions_monitored).toLocaleString()}</strong><small>across the evaluation window</small></div>
        <div><span>Active alerts</span><strong>{kpis.active_alerts ?? '—'}</strong><small className="positive">deterministic rule signals</small></div>
        <div><span>Cases created</span><strong>{kpis.cases ?? '—'}</strong><small>durable investigation records</small></div>
      </div>
      <div className="analytics-grid">
        <section className="surface trend-card"><div className="section-head"><div><div className="eyebrow">Signal volume</div><h3>Alerts raised</h3></div><span className="chip sage">stable</span></div><LineChart points={points} /></section>
        <section className="surface outcome-card"><div className="eyebrow">Disposition</div><h3>Case outcomes</h3><Donut segments={outcomes} /></section>
        <section className="surface rule-performance"><div className="section-head"><div><div className="eyebrow">Detection quality</div><h3>Rule performance</h3></div><span className="muted">Alerts · conversion</span></div>
          <div className="rule-bars">{(rules.length ? rules : FALLBACK_RULES.map((r, i) => ({ name: r.name, alerts: [12, 7, 5, 3][i], conversion_rate: [42, 29, 20, 8][i] }))).map((item) => <div key={item.id ?? item.rule_id ?? item.name}><div><span>{item.name ?? item.label ?? item.rule_id}</span><strong>{item.alerts ?? item.count} <small>· {item.conversion_rate ?? item.conversion ?? item.open ?? 0} open</small></strong></div><i><b style={{ width: `${number(item.alerts ?? item.count) / maxRule * 100}%` }} /></i></div>)}</div>
        </section>
      </div>
    </div>
  )
}

function RuleDrawer({ rule, role, onClose, onUpdated }) {
  const [candidate, setCandidate] = useState({ ...(rule.parameters ?? {}) })
  const [simulation, setSimulation] = useState(null)
  const [working, setWorking] = useState(null)
  const [error, setError] = useState(null)
  const editable = can(role, 'edit_rule')
  useEffect(() => { setCandidate({ ...(rule.parameters ?? {}) }); setSimulation(null); setError(null) }, [rule])
  const simulate = async () => {
    setWorking('simulate'); setError(null)
    try { setSimulation(await api(`/api/rules/${encodeURIComponent(rule.id)}/simulate`, { method: 'POST', body: { parameters: candidate }, role })) }
    catch (e) { setError(e.message) } finally { setWorking(null) }
  }
  const save = async () => {
    setWorking('save'); setError(null)
    try { await api(`/api/rules/${encodeURIComponent(rule.id)}`, { method: 'PATCH', body: { parameters: candidate }, role }); onUpdated('Rule parameters saved and versioned.'); onClose() }
    catch (e) { setError(e.message) } finally { setWorking(null) }
  }
  return (
    <div className="drawer-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <aside className="rule-drawer" role="dialog" aria-modal="true" aria-labelledby="rule-title">
        <div className="drawer-head"><div><span className={`severity-label ${rule.severity}`}><i />{rule.severity}</span><h2 id="rule-title">{rule.name}</h2><span className="mono">{rule.id} · {rule.policy_reference}</span></div><button className="icon-button" aria-label="Close rule editor" onClick={onClose}>×</button></div>
        <div className="drawer-scroll">
          <section><div className="eyebrow">Detection intent</div><p>{rule.description}</p><div className="rule-meta"><span>Category<strong>{rule.category ?? 'Behaviour monitoring'}</strong></span><span>Type<strong>Deterministic SQL</strong></span><span>State<strong>{rule.enabled ? 'Enabled' : 'Disabled'}</strong></span></div></section>
          <section><div className="eyebrow">Parameters</div><div className="parameter-grid">{Object.entries(candidate).map(([key, value]) => <label key={key}><span>{key.replaceAll('_', ' ')}</span><input type={typeof value === 'number' ? 'number' : 'text'} value={value} disabled={!editable} onChange={(e) => setCandidate({ ...candidate, [key]: typeof value === 'number' ? Number(e.target.value) : e.target.value })} /></label>)}</div></section>
          {!editable && <PermissionHint>Rule parameters are read-only for this persona. Switch to <strong>Rule Administrator</strong> to simulate changes.</PermissionHint>}
          {error && <div className="permission-hint danger" role="alert">{error}</div>}
          {simulation && <section className="simulation-result"><div className="eyebrow">Simulation result · no changes persisted</div><div><span><small>Baseline alerts</small><strong>{simulation.baseline?.alert_count ?? simulation.baseline?.match_count ?? simulation.baseline_alerts ?? '—'}</strong></span><span className="arrow">→</span><span><small>Candidate alerts</small><strong>{simulation.candidate?.alert_count ?? simulation.candidate?.match_count ?? simulation.candidate_alerts ?? simulation.match_count ?? '—'}</strong></span><span><small>Change</small><strong>{simulation.delta?.alert_count ?? simulation.delta?.match_count ?? simulation.delta ?? simulation.alert_delta ?? '—'}</strong></span></div><p>{simulation.summary ?? 'Candidate parameters were evaluated against the synthetic ledger.'}</p></section>}
        </div>
        <div className="drawer-actions"><button className="btn ghost" onClick={simulate} disabled={!can(role, 'simulate_rule') || working}>{working === 'simulate' ? <Spinner label="Simulating" /> : 'Simulate changes'}</button><button className="btn primary" onClick={save} disabled={!editable || working}>{working === 'save' ? <Spinner label="Saving" /> : 'Save rule'}</button></div>
      </aside>
    </div>
  )
}

function Rules({ data, role, reload }) {
  const rules = (data.rules ?? data ?? FALLBACK_RULES).map((item) => {
    const id = item.id ?? item.rule_id ?? item.rule
    const reference = FALLBACK_RULES.find((rule) => rule.id === id)
    return {
      ...item,
      id,
      name: item.name ?? item.label ?? reference?.name,
      description: item.description ?? item.what ?? reference?.description,
      severity: item.severity ?? reference?.severity ?? 'medium',
      category: item.category ?? reference?.category ?? 'Behaviour monitoring',
      policy_reference: item.policy_reference ?? reference?.policy_reference ?? 'Policy mapped',
    }
  })
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  const [notice, setNotice] = useState(null)
  const [updating, setUpdating] = useState(null)
  const view = rules.filter((rule) => `${rule.id} ${rule.name} ${rule.category}`.toLowerCase().includes(query.toLowerCase()))
  const toggle = async (event, rule) => {
    event.stopPropagation(); setUpdating(rule.id)
    try { await api(`/api/rules/${encodeURIComponent(rule.id)}`, { method: 'PATCH', body: { enabled: !rule.enabled }, role }); setNotice(`${rule.name} ${rule.enabled ? 'disabled' : 'enabled'}.`); reload() }
    catch (e) { setNotice(e.message) } finally { setUpdating(null) }
  }
  return (
    <div className="rules-view">
      <div className="subpage-head"><div><div className="eyebrow">Deterministic controls</div><h2>Detection rules</h2><p>Tune, test, and version explainable controls without changing source code.</p></div></div>
      {notice && <div className="success-toast" role="status">{notice}</div>}
      {!can(role, 'edit_rule') && <PermissionHint>This catalog is read-only. Switch to <strong>Rule Administrator</strong> to change or simulate controls.</PermissionHint>}
      <section className="surface rules-catalog">
        <div className="toolbar"><label className="search-field"><span>⌕</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search rules" aria-label="Search rules" /></label><span className="muted">{view.filter((rule) => rule.enabled).length} of {view.length} active</span></div>
        <div className="rule-list">{view.map((rule) => <article className="rule-row" key={rule.id}><span className={`rule-icon ${rule.severity ?? 'medium'}`}>⌁</span><button className="rule-open" onClick={() => setSelected(rule)}><span className="rule-copy"><strong>{rule.name}</strong><small>{rule.id} · {rule.policy_reference ?? 'Policy mapped'}</small><p>{rule.description}</p></span></button><span className={`chip ${rule.severity ?? 'medium'}`}>{rule.severity ?? 'monitor'}</span><span className="toggle-wrap"><span className="toggle-label">{rule.enabled ? 'Active' : 'Paused'}</span><button type="button" role="switch" aria-label={`${rule.enabled ? 'Disable' : 'Enable'} ${rule.name}`} aria-checked={rule.enabled} disabled={!can(role, 'edit_rule') || updating === rule.id} className={`switch ${rule.enabled ? 'on' : ''} ${updating === rule.id ? 'busy' : ''}`} onClick={(event) => toggle(event, rule)}><i /></button></span><button className="row-arrow icon-button" aria-label={`Open ${rule.name}`} onClick={() => setSelected(rule)}>→</button></article>)}</div>
        {!view.length && <EmptyState title="No matching rules" body="Clear the search to return to the complete catalog." />}
      </section>
      {selected && <RuleDrawer rule={selected} role={role} onClose={() => setSelected(null)} onUpdated={(message) => { setNotice(message); reload() }} />}
    </div>
  )
}

export default function IntelligencePage({ role }) {
  const [tab, setTab] = useState('analytics')
  const [period, setPeriod] = useState('90d')
  const [analytics, setAnalytics] = useState(null)
  const [rules, setRules] = useState(null)
  const [error, setError] = useState(null)
  const load = useCallback(() => {
    setError(null)
    Promise.all([api(`/api/analytics?period=${period}`, { role }), api('/api/rules', { role })])
      .then(([a, r]) => { setAnalytics(a); setRules(r) }).catch(setError)
  }, [period, role])
  useEffect(load, [load])
  if (error) return <ErrorState error={error} retry={load} />
  if (!analytics || !rules) return <PageSkeleton rows={4} />
  return (
    <div className="page intelligence-page">
      <header className="page-head compact"><div><div className="eyebrow">Control intelligence</div><h1>Analytics & rules</h1><p>Measure outcomes, then improve the controls that shape them.</p></div></header>
      <nav className="view-tabs" aria-label="Intelligence views"><button className={tab === 'analytics' ? 'active' : ''} onClick={() => setTab('analytics')}>Analytics</button><button className={tab === 'rules' ? 'active' : ''} onClick={() => setTab('rules')}>Rule administration</button></nav>
      {tab === 'analytics' ? <Analytics data={analytics} period={period} setPeriod={setPeriod} /> : <Rules data={rules} role={role} reload={load} />}
    </div>
  )
}

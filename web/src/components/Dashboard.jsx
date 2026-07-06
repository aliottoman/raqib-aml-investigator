import React, { useEffect, useRef, useState } from 'react'

const aed = (n) => `AED ${Math.round(Math.abs(n ?? 0)).toLocaleString('en-US')}`
const STATUS = { open: ['open', 'open'], sar_filed: ['crimson', 'SAR filed'], closed_no_sar: ['sage', 'closed · no SAR'] }

export default function Dashboard({ engine, onOpenCase }) {
  const [customers, setCustomers] = useState([])
  const [alerts, setAlerts] = useState([])
  const [sweep, setSweep] = useState(null)     // result of the last screening run
  const [scanIdx, setScanIdx] = useState(-1)   // which customer card is "being scanned"
  const timer = useRef(null)

  const load = () => {
    fetch('/api/portfolio').then((r) => r.json()).then((d) => setCustomers(d.customers))
    fetch('/api/alerts').then((r) => r.json()).then((d) => setAlerts(d.alerts))
  }
  useEffect(load, [])
  useEffect(() => () => clearInterval(timer.current), [])

  const runScreening = async () => {
    setAlerts([])
    setSweep(null)
    setScanIdx(0)
    // Sweep animation walks the grid while the rules actually run.
    timer.current = setInterval(() => setScanIdx((i) => i + 1), 170)
    const res = await fetch('/api/screening/run', { method: 'POST' }).then((r) => r.json())
    // let the walk reach the end before revealing the queue
    const remaining = Math.max(0, (customers.length - 1) * 170)
    setTimeout(() => {
      clearInterval(timer.current)
      setScanIdx(-1)
      setSweep(res)
      setAlerts(res.alerts.map((a) => ({ ...a, status: 'open', customer_name: a.customer_name })))
    }, remaining)
  }

  const hitByCustomer = {}
  for (const a of alerts) {
    if (!hitByCustomer[a.customer_id]) hitByCustomer[a.customer_id] = a.severity
  }
  const openAlerts = alerts.filter((a) => (a.status ?? 'open') === 'open')

  return (
    <div className="dash">
      <div className="dash-head">
        <div>
          <div className="eyebrow">Gulf Crescent Bank · financial crime operations</div>
          <h1>Portfolio screening</h1>
        </div>
        <div className="spacer" />
        <button className="btn primary" onClick={runScreening} disabled={scanIdx >= 0}>
          {scanIdx >= 0 ? 'Screening…' : 'Run AML screening'}
        </button>
      </div>

      <div className="stat-row">
        <div className="card stat"><div className="v">{customers.length}</div><div className="k">customers</div></div>
        <div className="card stat"><div className="v">{sweep ? sweep.transactions_scanned.toLocaleString() : '—'}</div><div className="k">transactions scanned</div></div>
        <div className="card stat"><div className="v">{sweep ? sweep.rules.length : 4}</div><div className="k">detection rules</div></div>
        <div className="card stat"><div className="v">{alerts.length ? openAlerts.length : '—'}</div><div className="k">open alerts</div></div>
      </div>

      <section>
        <div className="eyebrow" style={{ marginBottom: '0.6rem' }}>Customer book</div>
        <div className="grid">
          {customers.map((c, i) => (
            <div key={c.id}
                 className={`card cust ${i === scanIdx ? 'scanning' : ''} ${hitByCustomer[c.id] ? `hit-${hitByCustomer[c.id]}` : ''}`}>
              <div className="c-name">{c.name}</div>
              <div className="c-meta">{c.type} · {c.kyc_risk_rating} risk · since {String(c.onboarded).slice(0, 4)}</div>
              <div className="c-stats">
                <span>declared <b>{aed(c.declared_monthly_turnover_aed)}</b>/mo</span>
                <span>June credits <b>{aed(c.june_credits)}</b></span>
              </div>
              {hitByCustomer[c.id] && (
                <span className={`chip ${hitByCustomer[c.id]} flag`}>{hitByCustomer[c.id]}</span>
              )}
            </div>
          ))}
        </div>
      </section>

      {sweep && (
        <div className="sweepbar">
          <span className="chip sage">✓ sweep complete</span>
          <div className="rules-legend">
            {sweep.rules.map((r) => <span key={r.rule} className="chip plain" title={r.what}>{r.label}</span>)}
          </div>
        </div>
      )}

      {alerts.length > 0 && (
        <section>
          <div className="eyebrow" style={{ margin: '0.4rem 0 0.6rem' }}>Alert queue · by severity</div>
          {openAlerts.length > 0 && (
            <div className="reco-note" style={{ marginBottom: '0.6rem' }}>
              ⚑ Raqib recommends opening {openAlerts[0].id} first
            </div>
          )}
          <div className="queue">
            {alerts.map((a, i) => {
              const [tone, label] = STATUS[a.status ?? 'open'] ?? STATUS.open
              const investigable = engine === 'live' || a.id === 'RQB-2026-0347'
              return (
                <div key={a.id} className={`card alert-row ${i === 0 && (a.status ?? 'open') === 'open' ? 'reco' : ''}`}
                     style={{ animationDelay: `${i * 0.12}s` }}
                     onClick={() => onOpenCase(a.id)}>
                  <span className={`chip ${a.severity}`}>{a.severity}</span>
                  <div className="a-main">
                    <div className="a-name">{a.customer_name} <span className="a-id">· {a.id} · {a.rule}</span></div>
                    <div className="a-sum">{a.summary}</div>
                  </div>
                  {(a.status ?? 'open') !== 'open' && <span className={`chip ${tone}`}>{label}</span>}
                  {!investigable && <span className="chip plain">demo: view only</span>}
                  <button className="btn ghost" onClick={(e) => { e.stopPropagation(); onOpenCase(a.id) }}>
                    Open case →
                  </button>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {!alerts.length && !sweep && (
        <div className="chart-note" style={{ textAlign: 'center', padding: '1rem' }}>
          Run the AML screening to sweep the ledger with the detection rules — alerts will queue here.
        </div>
      )}
    </div>
  )
}

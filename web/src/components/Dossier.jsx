import React from 'react'

const aed = (n) => `AED ${Math.round(Math.abs(n)).toLocaleString('en-US')}`

// Pure-SVG bar chart of the June cash deposits against the reporting threshold.
function DepositChart({ deposits, threshold }) {
  const w = 640, h = 180, pad = 34
  const max = threshold * 1.15
  const bw = (w - pad * 2) / deposits.length
  const y = (v) => h - 24 - ((h - 52) * v) / max
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label="June cash deposits">
      <line x1={pad} x2={w - 8} y1={y(threshold)} y2={y(threshold)}
            stroke="var(--crimson)" strokeDasharray="5 4" strokeWidth="1.2" />
      <text x={w - 10} y={y(threshold) - 6} textAnchor="end" fontSize="10"
            fill="var(--crimson)" fontFamily="var(--mono)">
        CTR threshold {aed(threshold)}
      </text>
      {deposits.map((d, i) => (
        <g key={i}>
          <rect x={pad + i * bw + 3} y={y(d.amount_aed)} width={bw - 6}
                height={h - 24 - y(d.amount_aed)} rx="3"
                fill="var(--accent)" opacity="0.82" />
          <text x={pad + i * bw + bw / 2} y={h - 8} textAnchor="middle" fontSize="8.5"
                fill="var(--faint)" fontFamily="var(--mono)">
            {d.ts.slice(5, 10)}
          </text>
        </g>
      ))}
    </svg>
  )
}

export default function Dossier({ caseData, engine, onStart, onBack, embedded = false, canInvestigate: permission = true }) {
  const { alert, customer, threshold_aed, june_deposits, june_wires, is_flagship } = caseData
  const total = june_deposits.reduce((s, d) => s + d.amount_aed, 0)
  const canInvestigate = permission && (engine === 'live' || is_flagship)
  return (
    <div>
      {!embedded && <button className="btn ghost" style={{ marginBottom: '1rem' }} onClick={onBack}>← Alert queue</button>}
    <div className="dossier">
      <div className="stack">
        <section className="card card-pad">
          <div className="eyebrow">Suspicious activity alert · {alert.rule}</div>
          <div className="alert-head">
            <h2>{alert.id}</h2>
            <span className={`chip ${alert.status === 'open' ? 'open' : 'sage'}`}>
              {alert.status.replace(/_/g, ' ')}
            </span>
          </div>
          <div className="kv" style={{ marginBottom: '0.6rem' }}>
            <dt>Rule</dt><dd>{alert.rule}</dd>
            <dt>Raised</dt><dd>{alert.created}</dd>
          </div>
          <p className="alert-summary">{alert.summary}</p>
        </section>

        <section className="card card-pad">
          <div className="eyebrow">Subject</div>
          <h3 style={{ marginBottom: '0.55rem' }}>{customer.name}</h3>
          <div className="kv">
            <dt>Type</dt><dd>{customer.type}</dd>
            <dt>Country</dt><dd>{customer.country}</dd>
            <dt>KYC rating</dt><dd>{customer.kyc_risk_rating}</dd>
            <dt>Declared turnover</dt><dd>{aed(customer.declared_monthly_turnover_aed)}/month</dd>
            <dt>Onboarded</dt><dd>{customer.onboarded}</dd>
          </div>
        </section>

        <section className="card card-pad">
          <div className="eyebrow">Case documents · customer-submitted</div>
          <div className="doc-row"><span className="name">KYC profile</span><span className="chip plain">untrusted</span></div>
          <div className="doc-row"><span className="name">Wire instruction memo (PO-8871)</span><span className="chip plain">untrusted</span></div>
        </section>
      </div>

      <div className="stack">
        <section className="card card-pad">
          <div className="eyebrow">
            Recent cash deposits · {june_deposits.length ? `${june_deposits.length} since May · ${aed(total)} total` : 'none in window'}
          </div>
          {june_deposits.length > 0 ? (
            <>
              <div className="chart-wrap">
                <DepositChart deposits={june_deposits} threshold={threshold_aed} />
              </div>
              <div className="chart-note">
                Dashed line marks the AED {threshold_aed.toLocaleString()} cash-reporting threshold.
              </div>
            </>
          ) : (
            <div className="chart-note">No cash activity since May — see the alert summary and wires.</div>
          )}
        </section>

        <section className="card card-pad">
          <div className="eyebrow">Largest outbound wires since May</div>
          {june_wires.length > 0 ? (
            <table className="ledger">
              <thead><tr><th>Date</th><th>Counterparty</th><th>Country</th><th style={{ textAlign: 'right' }}>Amount</th></tr></thead>
              <tbody>
                {june_wires.map((wr, i) => (
                  <tr key={i}>
                    <td>{wr.ts.slice(0, 10)}</td>
                    <td>{wr.counterparty}</td>
                    <td>{wr.counterparty_country}</td>
                    <td className="num">−{aed(wr.amount_aed)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="chart-note">No outbound wires in the window.</div>
          )}
        </section>

        {onStart && <div className="start-row">
          <button className="btn primary" onClick={onStart} disabled={!canInvestigate}>
            Open investigation
          </button>
          <span className="chip plain">
            {canInvestigate
              ? (engine === 'live' ? 'agent will run live on OCI' : 'plays a recorded live run')
              : 'demo tape covers RQB-2026-0347 — live credentials investigate any alert'}
          </span>
        </div>}
      </div>
    </div>
    </div>
  )
}

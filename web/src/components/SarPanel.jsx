import React from 'react'

const aed = (n) => `AED ${Math.round(Math.abs(n)).toLocaleString('en-US')}`
const RISK_TONE = { low: 'var(--sage)', medium: 'var(--indigo)', high: 'var(--accent)', critical: 'var(--crimson)' }

// SVG arc dial for the 0-100 risk score.
function Dial({ score, level }) {
  const r = 74, c = Math.PI * r // half-circle circumference
  const filled = (c * score) / 100
  const tone = RISK_TONE[level] ?? 'var(--accent)'
  return (
    <div className="risk-dial">
      <svg width="200" height="118" viewBox="0 0 200 118">
        <path d="M 26 110 A 74 74 0 0 1 174 110" fill="none" stroke="var(--rule-2)" strokeWidth="13" strokeLinecap="round" />
        <path d="M 26 110 A 74 74 0 0 1 174 110" fill="none" stroke={tone} strokeWidth="13" strokeLinecap="round"
              strokeDasharray={`${filled} ${c}`} />
        <text x="100" y="88" textAnchor="middle" className="risk-num" fill="var(--ink)"
              fontFamily="var(--serif)" fontSize="40" fontWeight="600">{score}</text>
        <text x="100" y="108" textAnchor="middle" fontSize="10" letterSpacing="2"
              fill={tone} fontFamily="var(--mono)">{level.toUpperCase()} RISK</text>
      </svg>
    </div>
  )
}

export default function SarPanel({ sar, pii = [], onRestart, compact = false }) {
  return (
    <div className="sar">
      <div className="stack" style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
        <section className="card card-pad" style={{ textAlign: 'center' }}>
          <div className="eyebrow">Suspicious activity report · {sar.case_id}</div>
          <Dial score={sar.risk_score} level={sar.risk_level} />
          <div className="risk-cap" style={{ marginTop: '0.3rem' }}>
            {sar.sar_filing_required ? 'SAR filing required — §7.3, within 5 business days' : 'No SAR filing required'}
          </div>
        </section>

        <section className="card card-pad">
          <div className="eyebrow">Pattern</div>
          <div style={{ fontFamily: 'var(--serif)', fontSize: '1.02rem' }}>{sar.pattern_type}</div>
          <div className="kv" style={{ marginTop: '0.6rem' }}>
            <dt>Period</dt><dd>{sar.period}</dd>
            <dt>Total flows</dt><dd>{aed(sar.total_amount_aed)}</dd>
          </div>
        </section>

        <section className="card card-pad">
          <div className="eyebrow">Policy sections engaged</div>
          <div className="sec-chips">
            {(sar.policy_sections_engaged ?? []).map((s, i) => <span key={i} className="chip sage">{s}</span>)}
          </div>
        </section>

        {!compact && <section className="card card-pad">
          <div className="eyebrow">Export</div>
          <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
            <a className="btn primary" style={{ textDecoration: 'none' }} href="/api/report/pdf?lang=en">SAR PDF · English</a>
            <a className="btn ghost" style={{ textDecoration: 'none' }} href="/api/report/pdf?lang=ar">التقرير · عربي</a>
          </div>
          {onRestart && <button className="btn ghost" style={{ marginTop: '0.7rem', width: '100%' }} onClick={onRestart}>
            ← Back to alert queue
          </button>}
        </section>}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
        <section className="card card-pad">
          <div className="eyebrow">Subject</div>
          <h2 style={{ fontSize: '1.35rem' }}>{sar.subject}</h2>
        </section>

        <section className="card card-pad">
          <div className="eyebrow">Key findings</div>
          {(sar.key_findings ?? []).map((f, i) => (
            <div className="finding" key={i}><span className="n">{i + 1}</span><span>{f}</span></div>
          ))}
        </section>

        <section className="card card-pad">
          <div className="eyebrow">Counterparties</div>
          <table className="ledger">
            <thead><tr><th>Name</th><th>Country</th><th style={{ textAlign: 'right' }}>Total</th><th>Watchlist</th></tr></thead>
            <tbody>
              {(sar.counterparties ?? []).map((c, i) => (
                <tr key={i}>
                  <td>{c.name}</td>
                  <td>{c.country}</td>
                  <td className="num">{aed(c.total_aed)}</td>
                  <td>{c.watchlist_hit
                    ? <span className="chip crimson">hit</span>
                    : <span className="chip sage">clear</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card card-pad">
          <div className="eyebrow">Narrative</div>
          <div className="narrative">{sar.narrative}</div>
          <div className="pii-strip">
            <span className="chip indigo">PII scan · OCI Guardrails</span>
            {pii.length === 0 && <span className="chip sage">no PII detected</span>}
            {pii.map((h, i) => (
              <span key={i} className="chip plain">{h.label}: {h.text}</span>
            ))}
          </div>
        </section>

        <section className="card card-pad">
          <div className="eyebrow">Recommended actions</div>
          {(sar.recommended_actions ?? []).map((a, i) => (
            <div className="finding" key={i}><span className="n">→</span><span>{a}</span></div>
          ))}
        </section>
      </div>
    </div>
  )
}

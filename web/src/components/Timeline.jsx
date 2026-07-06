import React, { useEffect, useMemo, useRef, useState } from 'react'

const TOOL_META = {
  query_bank_ledger: { ico: '⌁', tone: 'indigo', title: 'Bank ledger', sub: 'governed SQL · analyst-approved' },
  search_aml_policy: { ico: '§', tone: 'sage', title: 'AML policy', sub: 'semantic retrieval · OCI embeddings' },
  read_case_document: { ico: '⎘', tone: 'accent', title: 'Case file', sub: 'screened by OCI Guardrails on read' },
  check_watchlist: { ico: '⚑', tone: 'crimson', title: 'Internal watchlist', sub: 'entity + related-party screening' },
  screen_adverse_media: { ico: '⌕', tone: 'accent', title: 'Adverse media', sub: 'xAI web_search · server-side tool' },
}

const CAPS = [
  ['memory', 'Conversation memory'],
  ['query_bank_ledger', 'Governed SQL'],
  ['search_aml_policy', 'Policy retrieval'],
  ['check_watchlist', 'Watchlist screening'],
  ['screen_adverse_media', 'Live web search'],
  ['code', 'Code interpreter'],
  ['guardrail', 'AI Guardrails'],
  ['sar', 'Structured SAR'],
]

// One-line outcome shown on a collapsed card.
function outcome(call, result, approval) {
  const r = result?.result
  if (!r) return approval?.result && !approval.result.approved ? ['declined', 'hit'] : ['…', '']
  if (r.error) return [r.error.slice(0, 60), 'hit']
  switch (call.name) {
    case 'query_bank_ledger': return [`${r.row_count} rows`, 'ok']
    case 'check_watchlist': return r.rows?.length ? ['WATCHLIST HIT', 'hit'] : ['clear', 'ok']
    case 'search_aml_policy': return [r.passages?.[0]?.section ?? 'no match', 'ok']
    case 'screen_adverse_media': return [/no credible|no significant|not find/i.test(r.summary ?? '') ? 'no adverse media found' : 'findings — expand', 'ok']
    case 'read_case_document': return [`${(r.text ?? '').length.toLocaleString()} chars read`, 'ok']
    default: return ['done', 'ok']
  }
}

function RowsTable({ result }) {
  if (result?.error) return <div className="guard flagged"><div><div className="g-title">Tool error</div><div className="g-body">{result.error}</div></div></div>
  const rows = result?.rows ?? []
  if (!rows.length) return <div className="chip sage" style={{ marginTop: '0.5rem' }}>no matching rows</div>
  const cols = result.columns ?? Object.keys(rows[0])
  return (
    <div style={{ overflowX: 'auto', marginTop: '0.6rem' }}>
      <table className="ledger">
        <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.slice(0, 4).map((r, i) => (
            <tr key={i}>{cols.map((c) => <td key={c} className={typeof r[c] === 'number' ? 'num' : ''}>{String(r[c] ?? '')}</td>)}</tr>
          ))}
        </tbody>
      </table>
      {rows.length > 4 && <div className="chart-note">+ {rows.length - 4} more rows returned to the agent</div>}
    </div>
  )
}

function ToolCard({ call, result, approval, approve, engine, active, canApprove = true }) {
  const meta = TOOL_META[call.name] ?? { ico: '·', tone: 'indigo', title: call.name, sub: '' }
  const pendingApproval = call.name === 'query_bank_ledger' && approval?.request && !approval?.result
  const [override, setOverride] = useState(null)
  const open = override ?? (pendingApproval || active || !result)
  const [note, tone] = outcome(call, result, approval)

  return (
    <section className={`card tool-card ${pendingApproval ? 'approval' : ''}`}>
      <button type="button" className="tool-head clickable" onClick={() => setOverride(!open)} aria-expanded={open}>
        <span className={`chev ${open ? 'open' : ''}`}>▶</span>
        <div className={`tool-ico ${meta.tone}`}>{meta.ico}</div>
        <div>
          <div className="t-name">{meta.title}</div>
          {open && <div className="t-sub">{meta.sub}</div>}
        </div>
        <div className="spacer" />
        {!open && <span className={`outcome ${tone}`}>{note}</span>}
        {approval?.result && open && (
          <span className={`approved-note ${approval.result.approved ? 'yes' : 'no'}`}>
            {approval.result.approved ? '✓ approved by analyst' : '✕ declined by analyst'}
          </span>
        )}
      </button>
      {open && (
        <div className="tool-body">
          {call.name === 'query_bank_ledger' && (
            <>
              {call.args.purpose && <div className="purpose">“{call.args.purpose}”</div>}
              <pre className="code">{call.args.sql}</pre>
            </>
          )}
          {call.name === 'search_aml_policy' && <div className="purpose">query: “{call.args.query}”</div>}
          {call.name === 'read_case_document' && <div className="purpose">document: {call.args.name}</div>}
          {(call.name === 'check_watchlist' || call.name === 'screen_adverse_media') && (
            <div className="purpose">entity: “{call.args.entity_name}”</div>
          )}

          {pendingApproval && (
            <div className="actions" style={{ padding: '0.7rem 0 0' }}>
              <button className="btn sage" disabled={!canApprove} title={!canApprove ? 'Switch to the AML Analyst persona to approve governed SQL' : undefined} onClick={(e) => { e.stopPropagation(); approve(true) }}>Approve & execute</button>
              {engine === 'live' && (
                <button className="btn crimson-o" onClick={(e) => { e.stopPropagation(); approve(false) }}>Decline</button>
              )}
            </div>
          )}

          {result && ['query_bank_ledger', 'check_watchlist'].includes(call.name) && <RowsTable result={result.result} />}
          {result && call.name === 'search_aml_policy' && (
            (result.result.passages ?? []).map((p, i) => (
              <div className="passage" key={i}>
                <div className="sec">{p.section} <span style={{ color: 'var(--faint)', fontWeight: 400 }}>· {p.source}</span></div>
                <div className="body">{p.text.split('\n').slice(1).join(' ').slice(0, 260)}…</div>
              </div>
            ))
          )}
          {result && call.name === 'screen_adverse_media' && !result.result.error && (
            <>
              <div style={{ fontSize: '0.87rem', whiteSpace: 'pre-wrap' }}>{result.result.summary}</div>
              {(result.result.citations ?? []).length > 0 && (
                <div className="citations">
                  {result.result.citations.map((u, i) => <a key={i} href={u} target="_blank" rel="noreferrer">{u.replace(/^https?:\/\//, '')}</a>)}
                </div>
              )}
            </>
          )}
          {result && call.name === 'read_case_document' && !result.result.error && (
            <div className="chip plain">{(result.result.text ?? '').length.toLocaleString()} chars read into case memory</div>
          )}
          {result && call.name === 'read_case_document' && result.result.error && (
            <div className="chip plain">{result.result.error}</div>
          )}
        </div>
      )}
    </section>
  )
}

function Thinking({ text }) {
  const [open, setOpen] = useState(false)
  return (
    <button type="button" className={`thinking evt ${open ? '' : 'clamped'}`} onClick={() => setOpen(!open)}
         title={open ? 'click to collapse' : 'click to expand'}>
      {text}
    </button>
  )
}

function CodeCard({ e, active }) {
  const [override, setOverride] = useState(null)
  const open = override ?? active
  return (
    <section className="card tool-card evt">
      <button type="button" className="tool-head clickable" onClick={() => setOverride(!open)} aria-expanded={open}>
        <span className={`chev ${open ? 'open' : ''}`}>▶</span>
        <div className="tool-ico indigo">λ</div>
        <div>
          <div className="t-name">Code interpreter</div>
          {open && <div className="t-sub">sandboxed Python · OCI managed container</div>}
        </div>
        <div className="spacer" />
        <span className="chip sage">executed</span>
      </button>
      {open && (
        <div className="tool-body">
          <pre className="code">{e.code}</pre>
          {e.output && <pre className="code" style={{ marginTop: '0.5rem', opacity: 0.85 }}>{e.output}</pre>}
        </div>
      )}
    </section>
  )
}

export default function Timeline({ events, running, engine, approve, caseData, onBack, embedded = false, canApprove = true }) {
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [events])

  // Merge tool_call / approval_* / tool_result by call id; keep feed order.
  const { items, byId, seen } = useMemo(() => {
    const byId = {}
    const items = []
    const seen = new Set()
    for (const e of events) {
      seen.add(e.type === 'tool_call' ? e.name : e.type)
      if (e.type === 'tool_call') {
        byId[e.id] = { call: e, approval: {} }
        items.push({ kind: 'tool', id: e.id })
      } else if (e.type === 'approval_request') {
        if (byId[e.id]) byId[e.id].approval.request = e
      } else if (e.type === 'approval_result') {
        if (byId[e.id]) byId[e.id].approval.result = e
      } else if (e.type === 'tool_result') {
        if (byId[e.id]) byId[e.id].result = e
      } else {
        items.push({ kind: e.type, e })
      }
    }
    return { items, byId, seen }
  }, [events])

  const lastCardIdx = useMemo(() => {
    for (let i = items.length - 1; i >= 0; i--) {
      if (items[i].kind === 'tool' || items[i].kind === 'code') return i
    }
    return -1
  }, [items])

  return (
    <div className={`room ${embedded ? 'embedded' : ''}`}>
      {!embedded && <aside className="rail">
        <section className="card card-pad">
          <div className="eyebrow">Case</div>
          <h3>{caseData?.alert?.id}</h3>
          <div style={{ fontSize: '0.84rem', color: 'var(--muted)', marginTop: '0.3rem' }}>
            {caseData?.customer?.name}
          </div>
          <button className="btn ghost" style={{ marginTop: '0.8rem', width: '100%' }} onClick={onBack}>
            ← Alert queue
          </button>
        </section>
        <section className="card card-pad">
          <div className="eyebrow">Enterprise AI in play</div>
          <div className="cap-list">
            {CAPS.map(([key, label]) => (
              <div key={key} className={`cap ${seen.has(key) ? 'on' : ''}`}>
                <span className="led" /> {label}
              </div>
            ))}
          </div>
        </section>
      </aside>}

      <div className="feed">
        {items.map((it, i) => {
          const active = i === lastCardIdx
          if (it.kind === 'tool') {
            const t = byId[it.id]
            return <div className="evt" key={i}><ToolCard {...t} approve={approve} engine={engine} active={active} canApprove={canApprove} /></div>
          }
          const e = it.e
          switch (e.type) {
            case 'step':
              return <div className="turn-rule evt" key={i}>{e.label ?? `Turn ${e.n}`}</div>
            case 'thinking':
              return <Thinking key={i} text={e.text} />
            case 'memory':
              return (
                <div className="evt" key={i}>
                  <span className="chip indigo">case memory opened · {e.conversation_id.slice(0, 22)}…</span>
                </div>
              )
            case 'guardrail':
              return e.injection_detected ? (
                <div className="guard flagged evt" key={i}>
                  <div>
                    <div className="g-title">⚠ OCI Guardrails — prompt injection detected</div>
                    <div className="g-body">
                      “{e.document}” · injection score {Number(e.prompt_injection_score).toFixed(2)}
                    </div>
                    {e.flagged_excerpt && <div className="excerpt">{e.flagged_excerpt}</div>}
                  </div>
                </div>
              ) : (
                <div className="guard clean slim evt" key={i}>
                  <div>✓ Guardrails — “{e.document}” clean · injection {Number(e.prompt_injection_score).toFixed(2)}</div>
                </div>
              )
            case 'code':
              return <CodeCard key={i} e={e} active={active} />
            case 'agent_message':
              return (
                <section className="card agent-final evt" key={i}>
                  <div className="eyebrow">Raqib — assessment to analyst</div>
                  {e.text}
                </section>
              )
            case 'error':
              return (
                <div className="guard flagged evt" key={i}>
                  <div><div className="g-title">Run error</div><div className="g-body">{e.message}</div></div>
                </div>
              )
            default:
              return null
          }
        })}
        {running && (
          <div className="waiting"><span className="spin" /> Raqib is working…</div>
        )}
        <div ref={endRef} />
      </div>
    </div>
  )
}

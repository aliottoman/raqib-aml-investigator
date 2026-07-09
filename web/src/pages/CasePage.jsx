import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api, can, pdfUrl } from '../api.js'
import { EmptyState, ErrorState, PageSkeleton, PermissionHint, Spinner } from '../components/States.jsx'
import Dossier from '../components/Dossier.jsx'
import Timeline from '../components/Timeline.jsx'
import SarPanel from '../components/SarPanel.jsx'
import { Link } from '../router.jsx'
import { useInvestigation } from '../useInvestigation.js'

const TABS = ['overview', 'investigation', 'sar', 'audit']

function detailToCaseData(detail) {
  const flattened = detail.case ?? detail
  const data = flattened.dossier ? { ...flattened, ...flattened.dossier } : flattened
  return {
    ...data,
    alert: data.alert ?? {
      id: data.id ?? data.case_id ?? data.alert_id,
      rule: data.rule,
      status: data.alert_status ?? data.status ?? 'open',
      created: data.created_at ?? data.created,
      summary: data.summary,
      severity: data.severity,
    },
    customer: data.customer ?? {
      id: data.customer_id,
      name: data.customer_name ?? data.subject,
      type: data.customer_type ?? 'Corporate',
      country: data.country ?? 'United Arab Emirates',
      kyc_risk_rating: data.kyc_risk_rating ?? 'medium',
      declared_monthly_turnover_aed: data.declared_monthly_turnover_aed ?? 0,
      onboarded: data.onboarded ?? '—',
    },
    threshold_aed: data.threshold_aed ?? 37_500,
    june_deposits: data.june_deposits ?? data.deposits ?? [],
    june_wires: data.june_wires ?? data.wires ?? [],
    is_flagship: data.is_flagship ?? true,
  }
}

function sarPayload(value) {
  if (!value) return null
  return value.report ?? value.sar ?? value.data ?? value
}

const TRANSITIONS = {
  open: ['investigating', 'closed'],
  investigating: ['open', 'draft_ready', 'closed'],
  draft_ready: ['investigating', 'pending_review', 'closed'],
  changes_requested: ['investigating', 'draft_ready', 'pending_review', 'closed'],
  pending_review: ['approved', 'changes_requested', 'closed'],
  approved: ['closed'],
  closed: ['open'],
}

function AuditTrail({ caseId, events, detail, role, status, onRefresh }) {
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState(null)
  const [nextStatus, setNextStatus] = useState('')
  const [reason, setReason] = useState('')
  const eventAudit = events.filter((event) => ['note', 'note_added', 'status_changed', 'case_transition', 'approval_result', 'sar_status', 'sar_saved', 'sar_submitted', 'sar_reviewed'].includes(event.type))
  const noteAudit = (detail.notes ?? []).map((item) => ({ ...item, type: 'note', actor_role: item.actor_role }))
  const audit = detail.audit ?? detail.audit_events ?? [...eventAudit, ...noteAudit]
  const addNote = async (event) => {
    event.preventDefault()
    if (!note.trim()) return
    setSaving(true)
    try {
      await api(`/api/cases/${encodeURIComponent(caseId)}/notes`, { method: 'POST', body: { text: note.trim() }, role })
      setNote('')
      setNotice('Note added to the case record.')
      onRefresh()
    } catch (error) { setNotice(error.message) } finally { setSaving(false) }
  }
  let allowed = TRANSITIONS[status] ?? []
  if (role === 'analyst') allowed = allowed.filter((item) => !['approved', 'changes_requested'].includes(item))
  if (role === 'reviewer') allowed = allowed.filter((item) => item !== 'investigating')
  if (!can(role, 'transition')) allowed = []
  const transition = async (event) => {
    event.preventDefault()
    if (!nextStatus) return
    setSaving(true)
    try {
      await api(`/api/cases/${encodeURIComponent(caseId)}/transition`, { method: 'POST', body: { status: nextStatus, reason: reason.trim() || undefined }, role })
      setNextStatus(''); setReason(''); setNotice(`Case moved to ${nextStatus.replaceAll('_', ' ')}.`); onRefresh()
    } catch (error) { setNotice(error.message) } finally { setSaving(false) }
  }
  return (
    <div className="audit-layout">
      <section className="surface audit-feed">
        <div className="section-head"><div><div className="eyebrow">Chronological record</div><h2>Audit trail</h2></div><span className="chip plain">append only</span></div>
        {(audit ?? []).length ? (audit ?? []).map((item, index) => (
          <div className="audit-item" key={item.id ?? index}>
            <span className={`audit-icon ${item.type ?? 'event'}`}>{item.type === 'note' ? 'N' : item.type === 'approval_result' ? '✓' : '·'}</span>
            <div><strong>{item.label ?? item.action ?? String(item.type ?? 'Case event').replaceAll('_', ' ')}</strong><p>{item.text ?? item.message ?? item.detail ?? item.reason ?? item.payload?.reason ?? item.payload?.note?.text ?? (item.payload?.from ? `${item.payload.from.replaceAll('_', ' ')} → ${item.payload.to.replaceAll('_', ' ')}` : 'Recorded in the case history.')}</p><small>{item.actor ?? item.role ?? item.actor_role ?? 'Raqib system'} · {String(item.created_at ?? item.timestamp ?? '').replace('T', ' ').slice(0, 16) || 'During this session'}</small></div>
          </div>
        )) : <EmptyState title="No audit entries yet" body="Investigation events and human decisions will appear here." />}
      </section>
      <aside className="surface note-panel">
        <div className="eyebrow">Case note</div><h3>Record an observation</h3><p>Notes are attributed to the selected demo persona.</p>
        {can(role, 'note') ? (
          <form onSubmit={addNote}>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows="5" placeholder="Add concise, evidence-based context…" aria-label="Case note" />
            <button className="btn primary" disabled={saving || !note.trim()}>{saving ? <Spinner label="Saving" /> : 'Add note'}</button>
            {notice && <small className="success-text">✓ {notice}</small>}
          </form>
        ) : <PermissionHint>This persona has read-only access to case notes.</PermissionHint>}
        {allowed.length > 0 && <form className="transition-form" onSubmit={transition}>
          <div className="eyebrow">Case lifecycle</div>
          <label>Move case to<select value={nextStatus} onChange={(e) => setNextStatus(e.target.value)}><option value="">Select status…</option>{allowed.map((item) => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}</select></label>
          {nextStatus && <label>Reason{nextStatus === 'closed' ? ' · required to close' : ''}<input value={reason} onChange={(e) => setReason(e.target.value)} required={nextStatus === 'closed'} placeholder={nextStatus === 'closed' ? 'Explain why this case can be closed…' : 'Short rationale (optional)'} /></label>}
          <button className="btn ghost" disabled={!nextStatus || saving || (nextStatus === 'closed' && !reason.trim())}>Update case status</button>
        </form>}
      </aside>
    </div>
  )
}

function SarWorkspace({ caseId, value, role, onRefresh }) {
  const source = sarPayload(value)
  const [draft, setDraft] = useState(source)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [comment, setComment] = useState('')
  const [notice, setNotice] = useState(null)
  useEffect(() => setDraft(source), [value])
  if (!draft) return <EmptyState eyebrow="SAR workspace" title="No report has been drafted" body="Complete the investigation first. Raqib will prepare a structured, evidence-linked draft for analyst review." />
  const workflowStatus = value?.workflow_status ?? value?.status ?? draft.status ?? 'draft'
  const progressIndex = ['approved', 'filed'].includes(workflowStatus) ? 3 : workflowStatus === 'pending_review' ? 1 : 0
  const finalOutput = ['approved', 'filed'].includes(workflowStatus)

  const mutate = async (path, options, message) => {
    setSaving(true); setNotice(null)
    try {
      await api(`/api/cases/${encodeURIComponent(caseId)}/sar${path}`, { ...options, role })
      setNotice(message); setEditing(false); await onRefresh()
    } catch (error) { setNotice(error.message) } finally { setSaving(false) }
  }
  const save = () => mutate('', { method: 'PUT', body: draft }, 'Draft saved to the case record.')
  const submit = () => mutate('/submit', { method: 'POST' }, 'SAR submitted for MLRO review.')
  const review = (decision) => mutate('/review', { method: 'POST', body: { decision, comment: comment.trim() || undefined } }, decision === 'approved' ? 'SAR approved.' : 'SAR returned for changes.')

  return (
    <div className="sar-workspace">
      <div className="sar-workflow-bar">
        <div><span className="eyebrow">Filing workflow</span><strong className={`status-label ${workflowStatus}`}>{String(workflowStatus).replaceAll('_', ' ')}</strong></div>
        <div className="workflow-steps" aria-label={`SAR status: ${workflowStatus}`}>
          {['draft', 'pending review', 'approved', 'export ready'].map((step, index) => <span key={step} className={index <= progressIndex ? 'done' : ''}><i />{step}</span>)}
        </div>
        <div className="sar-actions">
          {can(role, 'edit_sar') && <button className="btn ghost" onClick={() => setEditing((v) => !v)}>{editing ? 'Cancel edit' : 'Edit draft'}</button>}
          {can(role, 'submit_sar') && ['draft', 'changes_requested'].includes(workflowStatus) && <button className="btn primary" onClick={submit} disabled={saving}>Submit for review</button>}
        </div>
      </div>

      {notice && <div className={notice.includes('saved') || notice.includes('submitted') || notice.includes('approved') ? 'success-toast' : 'permission-hint'} role="status">{notice}</div>}
      {editing ? (
        <section className="surface sar-editor">
          <div className="section-head"><div><div className="eyebrow">Analyst draft</div><h2>Edit narrative</h2></div><span className="chip plain">versioned on save</span></div>
          <label>English narrative<textarea rows="12" value={draft.narrative ?? ''} onChange={(e) => setDraft({ ...draft, narrative: e.target.value })} /></label>
          <details><summary>Arabic filing narrative</summary><label lang="ar" dir="rtl">السرد العربي<textarea rows="10" dir="rtl" value={draft.narrative_ar ?? ''} onChange={(e) => setDraft({ ...draft, narrative_ar: e.target.value })} /></label></details>
          <div className="editor-actions"><button className="btn primary" onClick={save} disabled={saving}>{saving ? <Spinner label="Saving" /> : 'Save draft'}</button></div>
        </section>
      ) : <SarPanel sar={draft} pii={value?.pii_hits ?? []} compact />}

      {can(role, 'review_sar') && workflowStatus === 'pending_review' && (
        <section className="surface review-panel">
          <div><div className="eyebrow">MLRO decision</div><h2>Review the filing recommendation</h2><p>Confirm the evidence and narrative before approving the regulatory record.</p></div>
          <label>Review comment <textarea rows="3" value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Optional review rationale…" /></label>
          <div className="review-actions"><button className="btn ghost danger" onClick={() => review('changes_requested')} disabled={saving}>Request changes</button><button className="btn primary" onClick={() => review('approved')} disabled={saving}>Approve SAR</button></div>
        </section>
      )}
      <div className="export-row"><span>{finalOutput ? 'Approved output is available in required filing languages.' : 'Working copies are available for review before approval.'}</span><a className="btn ghost" href={pdfUrl(caseId, 'en', role)}>{finalOutput ? 'English PDF' : 'Draft PDF · English'}</a><a className="btn ghost" href={pdfUrl(caseId, 'ar', role)} lang="ar">{finalOutput ? 'التقرير العربي' : 'مسودة التقرير'}</a></div>
    </div>
  )
}

export default function CasePage({ caseId, role, health }) {
  const [detail, setDetail] = useState(null)
  const [storedEvents, setStoredEvents] = useState([])
  const [sar, setSar] = useState(null)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('overview')
  const investigation = useInvestigation(role)
  const engine = health?.live_available ? 'live' : 'demo'

  const load = useCallback(async () => {
    setError(null)
    try {
      const legacy = () => api(`/api/case?alert_id=${encodeURIComponent(caseId)}`, { role })
      const [nextDetail, nextEvents, nextSar] = await Promise.all([
        api(`/api/cases/${encodeURIComponent(caseId)}`, { role }).catch(legacy),
        api(`/api/cases/${encodeURIComponent(caseId)}/events`, { role }).catch(() => ({ events: [] })),
        api(`/api/cases/${encodeURIComponent(caseId)}/sar`, { role }).catch((e) => e.status === 404 ? null : Promise.reject(e)),
      ])
      setDetail(nextDetail)
      const history = nextEvents.events ?? nextEvents ?? []
      setStoredEvents(history)
      investigation.hydrate(history)
      setSar(nextSar)
    } catch (e) { setError(e) }
  }, [caseId, role]) // investigation callbacks are stable for a role

  useEffect(() => { setTab('overview') }, [caseId])
  useEffect(() => { investigation.reset(); setDetail(null); load() }, [caseId, role])
  const emittedSar = useMemo(() => investigation.events.filter((event) => event.type === 'sar').at(-1), [investigation.events])
  const pii = useMemo(() => investigation.events.filter((event) => event.type === 'pii').at(-1)?.hits ?? [], [investigation.events])
  const runDone = investigation.events.at(-1)?.type === 'done'
  useEffect(() => { if (runDone) load() }, [runDone])
  useEffect(() => {
    const emittedVersion = Number(emittedSar?.version ?? 0)
    const persistedVersion = Number(sar?.version ?? 0)
    if (emittedSar?.report && (!sar || emittedVersion > persistedVersion)) {
      setSar({
        case_id: caseId,
        version: emittedVersion || 1,
        status: emittedSar.status ?? 'draft',
        report: emittedSar.report,
        pii_hits: pii,
        source_run_id: emittedSar.run_id,
      })
    }
  }, [caseId, emittedSar, pii, sar])

  if (error) return <ErrorState error={error} retry={load} />
  if (!detail) return <PageSkeleton rows={3} />
  const data = detailToCaseData(detail)
  const status = detail.case_status ?? detail.status ?? data.alert.status ?? 'open'
  const events = investigation.events.length ? investigation.events : storedEvents
  // A run now outlives the socket that started it. Offer to reattach when this
  // socket dropped mid-run, or when the server still holds a running one.
  const droppedMidRun = investigation.connection === 'disconnected' && investigation.runId && !runDone
  const serverRun = detail.latest_run?.status === 'running' ? detail.latest_run.id : null
  const resumableRunId = droppedMidRun ? investigation.runId : (!investigation.running ? serverRun : null)

  return (
    <div className="page case-page">
      <div className="case-breadcrumb"><Link to="/cases">Cases</Link><span>/</span><span>{caseId}</span></div>
      <header className="case-header">
        <div className="case-identity"><span className={`severity-ribbon ${data.alert.severity ?? 'high'}`} /><div><div className="eyebrow">{caseId} · {data.alert.rule}</div><h1>{data.customer.name}</h1><p>{data.alert.summary}</p></div></div>
        <div className="case-header-meta"><div><small>Case status</small><span className={`status-label ${status}`}>{String(status).replaceAll('_', ' ')}</span></div><div><small>Owner</small><strong>{detail.owner ?? detail.assigned_to ?? 'AML Investigations'}</strong></div></div>
      </header>
      <nav className="case-tabs" aria-label="Case sections">
        {TABS.map((item) => <button key={item} className={tab === item ? 'active' : ''} aria-current={tab === item ? 'page' : undefined} onClick={() => setTab(item)}>{item}{item === 'investigation' && events.length > 0 && <span>{events.length}</span>}</button>)}
      </nav>

      <div className="case-content">
        {tab === 'overview' && <Dossier caseData={data} engine={engine} embedded canInvestigate={can(role, 'investigate')} onStart={can(role, 'investigate') ? () => { setTab('investigation'); investigation.start(engine, caseId) } : undefined} />}
        {tab === 'investigation' && resumableRunId && can(role, 'investigate') && (
          <div className="reconnect-banner" role="status">
            <span>A governed investigation is running for this case. Reconnect to follow it live and approve queries.</span>
            <button className="btn" onClick={() => investigation.resume(resumableRunId)}>Reconnect to live run</button>
          </div>
        )}
        {tab === 'investigation' && (events.length || investigation.running ? (
          <Timeline events={events} running={investigation.running} engine={engine} approve={investigation.approve} caseData={data} embedded canApprove={can(role, 'approve_sql')} />
        ) : (
          <EmptyState eyebrow="Governed investigation" title="This case has not been investigated" body="Raqib will gather policy, ledger, watchlist, document, and media evidence while keeping SQL execution under human control." action={can(role, 'investigate') ? <button className="btn primary" onClick={() => investigation.start(engine, caseId)}>Start investigation</button> : <PermissionHint>Switch to the AML Analyst persona to start an investigation.</PermissionHint>} />
        ))}
        {tab === 'sar' && <SarWorkspace caseId={caseId} value={sar} role={role} onRefresh={load} />}
        {tab === 'audit' && <AuditTrail caseId={caseId} events={events} detail={detail} role={role} status={status} onRefresh={load} />}
      </div>
    </div>
  )
}

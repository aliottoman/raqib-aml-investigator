import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { ErrorState, PageSkeleton } from '../components/States.jsx'

const CURRENT = [
  { id: 'workbench', name: 'Investigation workbench', service: 'React application', layer: 'experience', status: 'implemented', purpose: 'A role-aware operations workspace for alert triage, investigation, SAR review, analytics, and control governance.', inputs: 'Case and portfolio APIs', outputs: 'Human decisions and approvals', data: 'Confidential', rationale: 'A dedicated product interface makes complex investigations legible without exposing infrastructure detail.' },
  { id: 'api', name: 'Case orchestration API', service: 'FastAPI', layer: 'application', status: 'implemented', purpose: 'Coordinates cases, personas, approvals, report state, and the streamed investigation protocol.', inputs: 'Authenticated user actions', outputs: 'Case records and real-time events', data: 'Restricted', rationale: 'A typed service boundary separates operational workflow from AI and data adapters.' },
  { id: 'screening', name: 'Detection engine', service: 'Deterministic Python + SQL', layer: 'application', status: 'implemented', purpose: 'Evaluates explainable, versioned transaction-monitoring controls before AI is involved.', inputs: 'Customer and transaction ledger', outputs: 'Prioritized alerts with evidence', data: 'Restricted', rationale: 'Rules remain deterministic, testable, and independently auditable.' },
  { id: 'agent', name: 'Investigation agent', service: 'OCI Generative AI Responses API', layer: 'intelligence', status: 'implemented', purpose: 'Plans evidence gathering, invokes governed tools, reconciles findings, and produces a structured recommendation.', inputs: 'Case context and approved tool results', outputs: 'Evidence-linked assessment and SAR draft', data: 'Restricted', rationale: 'Structured responses provide a robust contract while the tool loop stays visible to the analyst.' },
  { id: 'guardrails', name: 'Content safeguards', service: 'OCI AI Guardrails', layer: 'intelligence', status: 'implemented', purpose: 'Screens untrusted customer documents for prompt injection and checks generated narrative for sensitive data.', inputs: 'Documents and draft output', outputs: 'Safety findings', data: 'Confidential', rationale: 'Untrusted evidence is isolated and screened before it enters case memory.' },
  { id: 'policy', name: 'Policy retrieval', service: 'OCI embeddings + isolated vector index', layer: 'intelligence', status: 'implemented', purpose: 'Retrieves citations only from the trusted AML policy corpus.', inputs: 'Investigation questions', outputs: 'Ranked policy passages', data: 'Internal', rationale: 'Separate corpora prevent customer-submitted evidence from being treated as policy.' },
  { id: 'ledger', name: 'Synthetic bank ledger', service: 'SQLite repository', layer: 'data', status: 'implemented', purpose: 'Persists synthetic customers, transactions, alerts, cases, event history, rule versions, and SAR drafts.', inputs: 'Synthetic bank activity', outputs: 'Read-only governed query results', data: 'Restricted', rationale: 'A local relational store proves domain behavior without requiring provisioned cloud infrastructure.' },
  { id: 'reports', name: 'Bilingual reports', service: 'ReportLab + Arabic shaping', layer: 'data', status: 'implemented', purpose: 'Produces English and Arabic regulatory report artifacts from the versioned case record.', inputs: 'Approved SAR schema', outputs: 'PDF filing copy', data: 'Restricted', rationale: 'Programmatic generation keeps multilingual output consistent with the reviewed record.' },
]

const TARGET = [
  { id: 'identity', name: 'Workforce identity', service: 'OCI IAM Identity Domains', layer: 'experience', status: 'next', purpose: 'Provides enterprise SSO, MFA, and group-to-role mapping for analysts, reviewers, auditors, and rule administrators.', inputs: 'Enterprise identity provider', outputs: 'Signed user identity and roles', data: 'Identity', rationale: 'Replaces the portfolio persona switcher without changing the authorization model.' },
  { ...CURRENT[0], status: 'ready', service: 'React on OCI Hosted Applications' },
  { ...CURRENT[1], status: 'ready', service: 'Containerized FastAPI on OCI Hosted Applications' },
  { id: 'queue', name: 'Durable investigation jobs', service: 'OCI Queue', layer: 'application', status: 'next', purpose: 'Decouples long-running agent work and supports resume, cancellation, and controlled retry.', inputs: 'Case investigation request', outputs: 'Ordered run work items', data: 'Restricted', rationale: 'Adds durability only when concurrent workloads require it.' },
  { ...CURRENT[2], status: 'ready', service: 'Containerized screening workers' },
  { ...CURRENT[3], status: 'ready' },
  { ...CURRENT[4], status: 'ready' },
  { id: 'vector', name: 'Managed policy store', service: 'OCI Generative AI Vector Store', layer: 'intelligence', status: 'next', purpose: 'Hosts approved, versioned policy sources with managed retrieval and citations.', inputs: 'Controlled policy releases', outputs: 'Grounded policy passages', data: 'Internal', rationale: 'Moves the isolated policy corpus to a managed service while preserving its trust boundary.' },
  { id: 'adb', name: 'Case & ledger database', service: 'Autonomous AI Database', layer: 'data', status: 'next', purpose: 'Becomes the canonical relational record for customers, cases, events, rule versions, approvals, and reports.', inputs: 'Bank adapters and case workflow', outputs: 'Governed relational data', data: 'Restricted', rationale: 'Provides enterprise persistence and security without changing repository contracts.' },
  { id: 'objects', name: 'Evidence vault', service: 'OCI Object Storage', layer: 'data', status: 'next', purpose: 'Stores evidence snapshots and immutable approved filing artifacts with retention policies.', inputs: 'Source evidence and final reports', outputs: 'Versioned, integrity-checked objects', data: 'Restricted', rationale: 'Separates large artifacts from transactional workflow records.' },
  { id: 'ops', name: 'Operations & security', service: 'Logging · Monitoring · Vault · Data Safe', layer: 'platform', status: 'optional', purpose: 'Centralizes secrets, security posture, service metrics, traces, and audit exports.', inputs: 'Runtime telemetry and secrets', outputs: 'Operational signals and controls', data: 'Operational', rationale: 'Introduced when the reference architecture moves into a managed customer environment.' },
]

const REGIONS = [
  { id: 'chicago', name: 'Chicago showcase', location: 'US Midwest', status: 'full', badge: 'Showcase', text: 'Broad model and tool coverage for the most complete technical walkthrough.', available: ['Responses orchestration', 'Agent tools', 'AI Guardrails', 'Managed retrieval'], note: 'Best for feature demonstrations where MEA data residency is not required.' },
  { id: 'riyadh', name: 'Saudi deployment', location: 'Riyadh', status: 'available', badge: 'Residency', text: 'MEA-resident profile for customer validation against locally available agentic services.', available: ['Regional deployment', 'Enterprise data services', 'Private networking', 'IAM controls'], note: 'Validate the selected model and every agent tool in the customer tenancy before deployment.' },
  { id: 'uae', name: 'UAE sovereign profile', location: 'Dubai / Abu Dhabi', status: 'constrained', badge: 'Blueprint', text: 'Strict residency blueprint with portable adapters and region-specific feature substitution.', available: ['Core OCI platform', 'Private data tier', 'Local evidence storage', 'Adapter-based AI tier'], note: 'Keep unsupported agentic capabilities visibly disabled until regional availability is confirmed.' },
]

const LAYERS = [
  ['experience', 'Analyst trust zone'],
  ['application', 'Application trust zone'],
  ['intelligence', 'Governed AI zone'],
  ['data', 'Protected data zone'],
  ['platform', 'Platform controls'],
]

function Node({ component, active, onSelect }) {
  return <button className={`arch-node ${active ? 'active' : ''}`} onClick={() => onSelect(component)}><span className={`node-state ${component.status}`} /><span><strong>{component.name}</strong><small>{component.service}</small></span></button>
}

function ArchitectureMap({ components, selected, onSelect }) {
  return (
    <div className="architecture-map">
      {LAYERS.map(([layer, label]) => {
        const items = components.filter((item) => item.layer === layer)
        if (!items.length) return null
        return <section className={`arch-layer ${layer}`} key={layer}><div className="layer-label"><span>{label}</span><small>{layer === 'data' ? 'encrypted at rest' : layer === 'intelligence' ? 'controlled tool access' : 'least privilege'}</small></div><div className="layer-nodes">{items.map((item) => <Node key={item.id} component={item} active={selected?.id === item.id} onSelect={onSelect} />)}</div></section>
      })}
      <div className="trust-legend"><span><i className="implemented" />Implemented</span><span><i className="ready" />Deployment ready</span><span><i className="next" />Next integration</span><span><i className="optional" />Optional</span></div>
    </div>
  )
}

function DetailPanel({ selected }) {
  return (
    <aside className="component-detail" aria-live="polite">
      <div className="eyebrow">Selected component</div><div className="component-title"><span className={`node-state ${selected.status}`} /><div><h2>{selected.name}</h2><p>{selected.service}</p></div></div>
      <p className="component-purpose">{selected.purpose}</p>
      <dl><div><dt>Receives</dt><dd>{selected.inputs}</dd></div><div><dt>Produces</dt><dd>{selected.outputs}</dd></div><div><dt>Classification</dt><dd>{selected.data}</dd></div><div><dt>Delivery state</dt><dd><span className={`status-label ${selected.status}`}>{selected.status}</span></dd></div></dl>
      <div className="rationale"><span>Why this choice</span><p>{selected.rationale}</p></div>
    </aside>
  )
}

export default function ArchitecturePage({ role, health }) {
  const [mode, setMode] = useState('current')
  const [selectedId, setSelectedId] = useState('agent')
  const [region, setRegion] = useState('chicago')
  const [remote, setRemote] = useState(null)
  const [error, setError] = useState(null)
  const load = useCallback(() => {
    api('/api/architecture', { role })
      .then(setRemote)
      .catch((e) => e.status === 404 ? setRemote({}) : setError(e))
  }, [role])
  useEffect(load, [load])
  const components = useMemo(() => {
    const supplied = remote?.[mode]?.components ?? remote?.components?.[mode]
    return supplied?.length ? supplied : mode === 'current' ? CURRENT : TARGET
  }, [remote, mode])
  useEffect(() => { if (!components.some((item) => item.id === selectedId)) setSelectedId(components[0]?.id) }, [components, selectedId])
  if (error) return <ErrorState error={error} retry={load} />
  if (!remote) return <PageSkeleton rows={4} />
  const selected = components.find((item) => item.id === selectedId) ?? components[0]
  const regionProfile = REGIONS.find((item) => item.id === region)

  return (
    <div className="page architecture-page">
      <header className="page-head architecture-head"><div><div className="eyebrow">Solution blueprint</div><h1>Transparent by design.</h1><p>Explore what runs today, what scales next, and where every trust boundary sits.</p></div><div className="mode-switch" aria-label="Architecture mode"><button className={mode === 'current' ? 'active' : ''} onClick={() => setMode('current')}>Current build</button><button className={mode === 'target' ? 'active' : ''} onClick={() => setMode('target')}>Target OCI</button></div></header>

      <section className="architecture-principle"><span className="principle-number">01</span><div><strong>Rules detect.</strong><p>Deterministic and explainable.</p></div><span>→</span><div><strong>AI investigates.</strong><p>Grounded and tool-governed.</p></div><span>→</span><div><strong>Humans decide.</strong><p>Explicitly and auditably.</p></div></section>

      <div className="arch-workspace">
        <section className="surface arch-canvas"><div className="section-head"><div><div className="eyebrow">{mode === 'current' ? 'Running implementation' : 'Production-shaped evolution'}</div><h2>{mode === 'current' ? 'Logical architecture' : 'OCI deployment architecture'}</h2></div><span className="chip plain">Select a component</span></div><ArchitectureMap components={components} selected={selected} onSelect={(item) => setSelectedId(item.id)} /></section>
        <DetailPanel selected={selected} />
      </div>

      <section className="surface region-section">
        <div className="section-head"><div><div className="eyebrow">Deployment profiles</div><h2>Region-aware by intent</h2><p>Availability is a design input, not a footnote.</p></div></div>
        <div className="region-layout"><div className="region-list" role="tablist">{REGIONS.map((item) => <button key={item.id} role="tab" aria-selected={region === item.id} className={region === item.id ? 'active' : ''} onClick={() => setRegion(item.id)}><span className={`region-dot ${item.status}`} /><span><strong>{item.name}</strong><small>{item.location}</small></span><span className="chip plain">{item.badge}</span></button>)}</div><div className="region-detail"><div className="region-status"><span className={`region-dot ${regionProfile.status}`} /><strong>{regionProfile.status === 'full' ? 'Full showcase profile' : regionProfile.status === 'available' ? 'Residency-oriented profile' : 'Capability-constrained blueprint'}</strong></div><h3>{regionProfile.name}</h3><p>{regionProfile.text}</p><div className="capability-list">{regionProfile.available.map((item) => <span key={item}>✓ {item}</span>)}</div><div className="region-note">{regionProfile.note}</div></div></div>
      </section>

      <details className="surface service-disclosure"><summary><span><span className={`service-dot ${health?.live_available ? 'live' : ''}`} /><strong>Runtime disclosure</strong></span><span>View technical metadata</span></summary><div><dl><div><dt>Execution mode</dt><dd>{health?.live_available ? 'Live OCI inference' : 'Recorded investigation tape'}</dd></div><div><dt>Region</dt><dd>{health?.region ?? 'Configured at deployment'}</dd></div><div><dt>Orchestrator</dt><dd>{health?.orchestrator_model ?? 'Configured at deployment'}</dd></div><div><dt>Guardrails</dt><dd>{health?.guardrails_available ? 'Available' : 'Recorded / adapter ready'}</dd></div></dl><p>Runtime metadata is intentionally kept out of the primary workflow. Operators see it here when they need technical assurance.</p></div></details>
    </div>
  )
}

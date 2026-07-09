import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { ErrorState, PageSkeleton } from '../components/States.jsx'

const DELIVERY = {
  implemented: { label: 'Implemented locally', tone: 'implemented' },
  'adapter-tested': { label: 'Adapter / contract tested', tone: 'ready' },
  'live-validated': { label: 'Live-validated snapshot', tone: 'implemented' },
  target: { label: 'Target integration', tone: 'next' },
  optional: { label: 'Optional target', tone: 'optional' },
}

function delivery(status) {
  return DELIVERY[status] ?? { label: status, tone: 'optional' }
}

const CURRENT = [
  { id: 'workbench', name: 'Investigation workbench', service: 'React application', layer: 'experience', status: 'implemented', purpose: 'A role-aware operations workspace for alert triage, investigation, SAR review, analytics, and control governance.', inputs: 'Case and portfolio APIs', outputs: 'Human decisions and approvals', data: 'Confidential', rationale: 'A dedicated product interface makes complex investigations legible without exposing infrastructure detail.' },
  { id: 'api', name: 'Case orchestration API', service: 'FastAPI', layer: 'application', status: 'implemented', purpose: 'Coordinates cases, simulated personas, approvals, report state, and the streamed investigation protocol.', inputs: 'Role-labelled user actions', outputs: 'Case records and real-time events', data: 'Restricted', rationale: 'A typed service boundary separates operational workflow from AI and data adapters; production authentication is a target integration.' },
  { id: 'screening', name: 'Detection engine', service: 'Deterministic Python + SQL', layer: 'application', status: 'implemented', purpose: 'Evaluates explainable, configurable transaction-monitoring controls before AI is involved.', inputs: 'Customer and transaction ledger', outputs: 'Prioritized alerts with evidence', data: 'Restricted', rationale: 'Rules remain deterministic and testable. The UI exposes current parameters and a revision counter, not prior rule configurations.' },
  { id: 'agent', name: 'Investigation agent', service: 'OCI Generative AI Responses API', layer: 'intelligence', status: 'live-validated', purpose: 'Plans evidence gathering, invokes governed tools, reconciles findings, and produces a structured recommendation.', inputs: 'Case context and approved tool results', outputs: 'Evidence-linked assessment and SAR draft', data: 'Restricted', rationale: 'A four-case live evaluation snapshot is preserved in EVALS.md. It is historical evidence, not a claim that the current environment is connected or production-validated.' },
  { id: 'guardrails', name: 'OCI content safeguards', service: 'OCI AI Guardrails', layer: 'intelligence', status: 'live-validated', purpose: 'Screens untrusted customer documents for prompt injection and checks generated narrative for sensitive data.', inputs: 'Documents and draft output', outputs: 'Safety findings', data: 'Confidential', rationale: 'EVALS.md preserves the last OCI-only live sweep separately from the current offline local-heuristic result.' },
  { id: 'heuristic', name: 'Local injection heuristic', service: 'Deterministic layer 1b', layer: 'intelligence', status: 'implemented', purpose: 'Adds a credential-free prompt-injection check for known attack shapes.', inputs: 'Untrusted document text', outputs: 'Detection score and signal', data: 'Confidential', rationale: 'The current 21/21 attack and 0/3 benign result is a fixed-corpus offline regression check, not evidence of general attack coverage.' },
  { id: 'policy', name: 'Local policy retrieval', service: 'OCI embeddings + isolated vector index', layer: 'intelligence', status: 'live-validated', purpose: 'Retrieves citations only from the trusted AML policy corpus.', inputs: 'Investigation questions', outputs: 'Ranked policy passages', data: 'Internal', rationale: 'The historical live golden suite exercised policy citations while keeping customer evidence outside this index.' },
  { id: 'managed-policy', name: 'Managed policy retrieval adapter', service: 'OCI Vector Store / File Search', layer: 'intelligence', status: 'adapter-tested', purpose: 'Maps managed search results into the same citation contract as local policy retrieval.', inputs: 'Controlled policy sections and search query', outputs: 'Source, section, and text citations', data: 'Internal', rationale: 'The adapter and provisioning path are implemented and contract-tested with fakes. No live managed-retrieval validation is recorded.' },
  { id: 'ledger', name: 'Synthetic bank ledger', service: 'SQLite repository', layer: 'data', status: 'implemented', purpose: 'Persists synthetic customers, transactions, alerts, cases, case events, SAR records, current rule configuration, and simulation runs.', inputs: 'Synthetic bank activity', outputs: 'Application state and governed query results', data: 'Restricted', rationale: 'This is ordinary local SQLite persistence. Encryption, tamper evidence, immutable/WORM retention, and integrity-protected export are not demonstrated.' },
  { id: 'reports', name: 'Bilingual reports', service: 'ReportLab + Arabic shaping', layer: 'data', status: 'implemented', purpose: 'Produces English and Arabic report artifacts from the latest reviewed SAR record.', inputs: 'Reviewed SAR schema', outputs: 'PDF report artifact', data: 'Restricted', rationale: 'Programmatic generation keeps multilingual output consistent with the reviewed record. The UI does not expose a SAR-version history browser.' },
]

const TARGET = [
  { id: 'identity', name: 'Workforce identity', service: 'OCI IAM Identity Domains', layer: 'experience', status: 'target', purpose: 'Provides enterprise SSO, MFA, and group-to-role mapping for analysts, reviewers, auditors, and rule administrators.', inputs: 'Enterprise identity provider', outputs: 'Signed user identity and roles', data: 'Identity', rationale: 'Replaces the portfolio persona switcher with identity-derived authorization.' },
  { ...CURRENT[0], status: 'target', service: 'React on a governed OCI runtime', rationale: 'The React application exists; this hosted deployment profile is a target and has not been validated here.' },
  { ...CURRENT[1], status: 'target', service: 'Containerized FastAPI on a governed OCI runtime', rationale: 'The FastAPI service exists; production identity, secrets, scaling, and hosting remain target integrations.' },
  { id: 'queue', name: 'Durable investigation jobs', service: 'OCI Queue', layer: 'application', status: 'target', purpose: 'Decouples long-running agent work and supports resume, cancellation, and controlled retry.', inputs: 'Case investigation request', outputs: 'Ordered run work items', data: 'Restricted', rationale: 'Adds durable, multi-instance execution for a controlled pilot.' },
  { ...CURRENT[2], status: 'target', service: 'Containerized screening workers', rationale: 'The rules exist locally; managed worker deployment and operations remain a target.' },
  { ...CURRENT[3] },
  { ...CURRENT[4] },
  { id: 'vector', name: 'Managed policy store deployment', service: 'OCI Generative AI Vector Store / File Search', layer: 'intelligence', status: 'target', purpose: 'Hosts approved policy sources with managed retrieval and citations.', inputs: 'Controlled policy releases', outputs: 'Grounded policy passages', data: 'Internal', rationale: 'The application adapter is contract-tested, while provisioning and search against a live managed store still require validation.' },
  { id: 'adb', name: 'Case & ledger database', service: 'Autonomous AI Database', layer: 'data', status: 'target', purpose: 'Becomes the canonical relational record for customers, cases, events, approvals, current controls, and reports.', inputs: 'Bank adapters and case workflow', outputs: 'Governed relational data', data: 'Restricted', rationale: 'Production persistence, encryption, backup, retention, and access controls must be designed and validated in the customer environment.' },
  { id: 'objects', name: 'Evidence vault', service: 'OCI Object Storage', layer: 'data', status: 'target', purpose: 'Stores evidence snapshots and approved report artifacts under customer-defined retention and integrity controls.', inputs: 'Source evidence and final reports', outputs: 'Governed objects', data: 'Restricted', rationale: 'Immutable retention or WORM behavior is a target policy choice, not a capability demonstrated by the current build.' },
  { id: 'ops', name: 'Operations & security', service: 'Logging · Monitoring · Vault · Data Safe', layer: 'platform', status: 'optional', purpose: 'Centralizes secrets, security posture, service metrics, traces, and audit exports.', inputs: 'Runtime telemetry and secrets', outputs: 'Operational signals and controls', data: 'Operational', rationale: 'Introduced when the reference architecture moves into a managed customer environment.' },
]

const REGIONS = [
  { id: 'chicago', name: 'Chicago showcase', location: 'US Midwest', status: 'full', badge: 'Showcase', text: 'A discussion profile based on the historically exercised live agent path.', available: ['Responses orchestration', 'Agent tools', 'Historical AI Guardrails snapshot', 'Managed-retrieval adapter (not live-validated)'], note: 'Service and model availability must be rechecked before each demonstration; this is not proof of a currently connected tenancy.' },
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
  const state = delivery(component.status)
  return <button className={`arch-node ${active ? 'active' : ''}`} onClick={() => onSelect(component)}><span className={`node-state ${state.tone}`} /><span><strong>{component.name}</strong><small>{component.service}</small></span></button>
}

function ArchitectureMap({ components, selected, onSelect }) {
  return (
    <div className="architecture-map">
      {LAYERS.map(([layer, label]) => {
        const items = components.filter((item) => item.layer === layer)
        if (!items.length) return null
        return <section className={`arch-layer ${layer}`} key={layer}><div className="layer-label"><span>{label}</span><small>{layer === 'data' ? 'protection level varies by deployment' : layer === 'intelligence' ? 'controlled tool access' : 'role-aware boundary'}</small></div><div className="layer-nodes">{items.map((item) => <Node key={item.id} component={item} active={selected?.id === item.id} onSelect={onSelect} />)}</div></section>
      })}
      <div className="trust-legend"><span><i className="implemented" />Implemented</span><span><i className="ready" />Adapter / contract tested</span><span><i className="implemented" />Live-validated snapshot</span><span><i className="next" />Target integration</span><span><i className="optional" />Optional target</span></div>
    </div>
  )
}

function DetailPanel({ selected }) {
  const state = delivery(selected.status)
  return (
    <aside className="component-detail" aria-label={`${selected.name} details`} aria-live="polite">
      <div className="eyebrow">Selected component</div><div className="component-title"><span className={`node-state ${state.tone}`} /><div><h2>{selected.name}</h2><p>{selected.service}</p></div></div>
      <p className="component-purpose">{selected.purpose}</p>
      <dl><div><dt>Receives</dt><dd>{selected.inputs}</dd></div><div><dt>Produces</dt><dd>{selected.outputs}</dd></div><div><dt>Classification</dt><dd>{selected.data}</dd></div><div><dt>Delivery state</dt><dd><span className={`status-label ${state.tone}`}>{state.label}</span></dd></div></dl>
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
      <header className="page-head architecture-head"><div><div className="eyebrow">Solution blueprint</div><h1>Transparent by design.</h1><p>Separate the current build, contract-tested adapters, preserved live evidence, and target integrations.</p></div><div className="mode-switch" aria-label="Architecture mode"><button className={mode === 'current' ? 'active' : ''} onClick={() => setMode('current')}>Current build</button><button className={mode === 'target' ? 'active' : ''} onClick={() => setMode('target')}>Target OCI</button></div></header>

      <section className="architecture-principle"><span className="principle-number">01</span><div><strong>Rules detect.</strong><p>Deterministic and explainable.</p></div><span>→</span><div><strong>AI investigates.</strong><p>Grounded and tool-governed.</p></div><span>→</span><div><strong>Humans decide.</strong><p>Explicitly, with case events recorded.</p></div></section>

      <div className="arch-workspace">
        <section className="surface arch-canvas"><div className="section-head"><div><div className="eyebrow">{mode === 'current' ? 'Current reference build' : 'Production-shaped evolution'}</div><h2>{mode === 'current' ? 'Logical architecture' : 'OCI deployment architecture'}</h2></div><span className="chip plain">Select a component</span></div><ArchitectureMap components={components} selected={selected} onSelect={(item) => setSelectedId(item.id)} /></section>
        <DetailPanel selected={selected} />
      </div>

      <section className="surface region-section">
        <div className="section-head"><div><div className="eyebrow">Deployment profiles</div><h2>Region-aware by intent</h2><p>Availability is a design input, not a footnote.</p></div></div>
        <div className="region-layout"><div className="region-list" role="tablist">{REGIONS.map((item) => <button key={item.id} role="tab" aria-selected={region === item.id} className={region === item.id ? 'active' : ''} onClick={() => setRegion(item.id)}><span className={`region-dot ${item.status}`} /><span><strong>{item.name}</strong><small>{item.location}</small></span><span className="chip plain">{item.badge}</span></button>)}</div><div className="region-detail"><div className="region-status"><span className={`region-dot ${regionProfile.status}`} /><strong>{regionProfile.status === 'full' ? 'Full showcase profile' : regionProfile.status === 'available' ? 'Residency-oriented profile' : 'Capability-constrained blueprint'}</strong></div><h3>{regionProfile.name}</h3><p>{regionProfile.text}</p><div className="capability-list">{regionProfile.available.map((item) => <span key={item}>✓ {item}</span>)}</div><div className="region-note">{regionProfile.note}</div></div></div>
      </section>

      <details className="surface service-disclosure"><summary><span><span className={`service-dot ${health?.live_available ? 'live' : ''}`} /><strong>Runtime disclosure</strong></span><span>View technical metadata</span></summary><div><dl><div><dt>Execution mode</dt><dd>{health?.live_available ? 'Configured for live OCI inference' : 'Recorded investigation tape'}</dd></div><div><dt>Region</dt><dd>{health?.region ?? 'Not connected in this session'}</dd></div><div><dt>Orchestrator</dt><dd>{health?.orchestrator_model ?? 'Not active in recorded mode'}</dd></div><div><dt>OCI Guardrails</dt><dd>{health?.guardrails_available ? 'Configured; see EVALS.md for validation provenance' : 'Not active in this session'}</dd></div><div><dt>Managed File Search</dt><dd>Adapter contract-tested; live validation not recorded</dd></div><div><dt>Local persistence</dt><dd>SQLite; encryption and immutable/WORM storage not asserted</dd></div></dl><p>Configuration availability is not the same as successful live validation. EVALS.md records the date, layer, and limitations of the preserved evaluation snapshots.</p></div></details>
    </div>
  )
}

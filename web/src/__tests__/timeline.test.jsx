import React from 'react'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Timeline from '../components/Timeline.jsx'

describe('investigation timeline', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('renders the agent assessment as safe structured text instead of raw markdown markers', () => {
    render(
      <Timeline
        embedded
        running={false}
        engine="demo"
        approve={() => {}}
        events={[{
          type: 'agent_message',
          text: '**Case RQB-2026-0347**\n\n- **Assessment**: high risk\n- Evidence reconciled',
        }]}
      />,
    )

    expect(screen.getByText('Case RQB-2026-0347', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('Assessment', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('Evidence reconciled')).toBeInTheDocument()
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument()
  })

  it('renders multimodal extraction results instead of the raw tool name', () => {
    render(
      <Timeline embedded running={false} engine="live" approve={() => {}}
        events={[
          { type: 'tool_call', id: 'x1', name: 'extract_document', args: { name: 'wire_memo' } },
          { type: 'tool_result', id: 'x1', name: 'extract_document', result: {
            name: 'wire_memo', doc_type: 'wire authorization',
            fields: { beneficiary: 'Orbit Precious Metals DMCC' }, text: 'scanned body', backend: 'demo' } },
        ]} />,
    )
    expect(screen.getByText('Document extraction')).toBeInTheDocument()
    expect(screen.getByText('Orbit Precious Metals DMCC')).toBeInTheDocument()
    expect(screen.queryByText('extract_document')).not.toBeInTheDocument()
  })

  it('renders counterparty enrichment evidence rather than a bare tool name', () => {
    render(
      <Timeline embedded running={false} engine="live" approve={() => {}}
        events={[
          { type: 'tool_call', id: 'e1', name: 'enrich_counterparty_context', args: { entity_name: 'Orbit Precious Metals DMCC' } },
          { type: 'tool_result', id: 'e1', name: 'enrich_counterparty_context', result: {
            entity_name: 'Orbit Precious Metals DMCC', watchlist: { rows: [], columns: [] },
            adverse_media: { summary: 'Gold-invoicing inquiry noted.', citations: ['synthetic://intel/orbit'] },
            risk_factors: ['Adverse-media coverage found'], untrusted: true, backend: 'demo' } },
        ]} />,
    )
    expect(screen.getByText('Counterparty context')).toBeInTheDocument()
    expect(screen.getByText('Adverse-media coverage found')).toBeInTheDocument()
    expect(screen.getByText('Gold-invoicing inquiry noted.')).toBeInTheDocument()
    expect(screen.queryByText('enrich_counterparty_context')).not.toBeInTheDocument()
  })
})

import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import CasePage from '../pages/CasePage.jsx'
import { mockJsonFetch } from './mockFetch.js'

const REPORT = {
  case_id: 'RQB-2026-0347',
  subject: 'Al Rashidi Trading FZE',
  risk_level: 'high',
  risk_score: 84,
  pattern_type: 'Structuring followed by layering',
  period: '2026-06-08 to 2026-06-19',
  total_amount_aed: 771200,
  counterparties: [],
  policy_sections_engaged: ['§4.2'],
  key_findings: ['Repeated sub-threshold cash deposits.'],
  narrative: 'Synthetic investigation narrative.',
  narrative_ar: 'سرد التحقيق التجريبي.',
  recommended_actions: ['Maintain enhanced monitoring.'],
  sar_filing_required: true,
}

describe('SAR lifecycle reconciliation', () => {
  it('keeps persisted pending-review state when investigation history is hydrated', async () => {
    const user = userEvent.setup()
    mockJsonFetch([
      {
        url: '/api/cases/RQB-2026-0347',
        response: {
          id: 'RQB-2026-0347', status: 'pending_review', severity: 'critical', owner: 'AML Investigations',
          dossier: {
            alert: { id: 'RQB-2026-0347', rule: 'CASH-VELOCITY-04', status: 'pending_review', severity: 'critical', summary: 'Synthetic alert.', created: '2026-06-18' },
            customer: { id: 1017, name: 'Al Rashidi Trading FZE', type: 'Company', country: 'AE', kyc_risk_rating: 'Medium', declared_monthly_turnover_aed: 150000, onboarded: '2025-11-03' },
            threshold_aed: 37500, june_deposits: [], june_wires: [], is_flagship: true,
          },
        },
      },
      { url: '/api/cases/RQB-2026-0347/events', response: { events: [{ type: 'sar', event_id: 19, version: 1, status: 'draft', report: REPORT }] } },
      { url: '/api/cases/RQB-2026-0347/sar', response: { case_id: 'RQB-2026-0347', version: 1, status: 'pending_review', report: REPORT, pii_hits: [] } },
    ])

    const { rerender } = render(<CasePage caseId="RQB-2026-0347" role="analyst" health={{ live_available: false }} />)
    await user.click(await screen.findByRole('button', { name: 'sar' }))

    await waitFor(() => expect(screen.getAllByText('pending review').length).toBeGreaterThan(0))
    expect(screen.queryByRole('button', { name: 'Submit for review' })).not.toBeInTheDocument()
    expect(screen.getByText('Working copies are available for review before approval.')).toBeInTheDocument()

    rerender(<CasePage caseId="RQB-2026-0347" role="reviewer" health={{ live_available: false }} />)
    expect(await screen.findByText('MLRO decision')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve SAR' })).toBeInTheDocument()
  })
})

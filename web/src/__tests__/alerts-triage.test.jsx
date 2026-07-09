import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import AlertsPage from '../pages/AlertsPage.jsx'
import { mockJsonFetch } from './mockFetch.js'

const ALERTS = [
  { id: 'RQB-2026-0347', customer_name: 'Al Rashidi Trading FZE', rule: 'CASH-VELOCITY-04',
    severity: 'critical', summary: 'Sub-threshold cash structuring', created: '2026-06-18', status: 'open',
    workflow_status: 'open', priority: 'urgent', owner: 'Triage Desk 1' },
  { id: 'RQB-2026-0422', customer_name: 'Cedarwood Interiors LLC', rule: 'WATCHLIST-PROX-01',
    severity: 'high', summary: 'Wire to a watchlisted counterparty', created: '2026-06-17', status: 'open',
    workflow_status: 'open', priority: 'high', owner: null },
]
const TRIAGE = {
  total: 9, active: 9, unassigned: 9,
  by_severity: { critical: 2, high: 3, medium: 2, low: 2 },
  by_rule: {}, by_status: { open: 9 }, by_priority: {}, by_owner: {},
}

const queueRoutes = (extra = []) => [
  { url: '/api/alerts', response: { alerts: ALERTS } },
  { url: '/api/triage', response: TRIAGE },
  ...extra,
]

describe('alert queue triage', () => {
  it('lets an analyst bulk-assign selected cases', async () => {
    const user = userEvent.setup()
    const fetchMock = mockJsonFetch(queueRoutes([
      { method: 'POST', url: '/api/cases/bulk',
        response: { action: 'assign', updated: ['RQB-2026-0347'], skipped: [], updated_count: 1, skipped_count: 0 } },
    ]))
    render(<AlertsPage role="analyst" />)

    expect(await screen.findByRole('heading', { name: 'Alert queue' })).toBeInTheDocument()
    expect(screen.getByLabelText('Queue summary')).toBeInTheDocument()
    expect(screen.getByText('Triage Desk 1')).toBeInTheDocument()
    expect(screen.getByText('urgent')).toBeInTheDocument()

    // No bulk bar until something is selected.
    expect(screen.queryByRole('region', { name: 'Bulk triage actions' })).toBeNull()
    await user.click(screen.getByLabelText('Select RQB-2026-0347'))
    const bar = screen.getByRole('region', { name: 'Bulk triage actions' })
    expect(bar).toBeInTheDocument()

    await user.type(screen.getByLabelText('Owner'), 'Triage Desk 3')
    await user.click(screen.getByRole('button', { name: 'Assign' }))

    const call = fetchMock.mock.calls.find(([url, init]) => url === '/api/cases/bulk' && init?.method === 'POST')
    expect(call).toBeDefined()
    expect(call[1].headers).toEqual(expect.objectContaining({ 'X-Raqib-Role': 'analyst' }))
    expect(JSON.parse(call[1].body)).toEqual({
      case_ids: ['RQB-2026-0347'], action: 'assign', owner: 'Triage Desk 3',
    })
  })

  it('select-all covers the visible queue', async () => {
    const user = userEvent.setup()
    mockJsonFetch(queueRoutes())
    render(<AlertsPage role="analyst" />)

    await screen.findByRole('heading', { name: 'Alert queue' })
    await user.click(screen.getByLabelText('Select all in view'))
    expect(screen.getByLabelText('Select RQB-2026-0347')).toBeChecked()
    expect(screen.getByLabelText('Select RQB-2026-0422')).toBeChecked()
    expect(screen.getByRole('region', { name: 'Bulk triage actions' })).toBeInTheDocument()
  })

  it('requires rationale review and reports every skipped close', async () => {
    const user = userEvent.setup()
    const skippedReason = 'Cannot transition from pending review to closed'
    const fetchMock = mockJsonFetch(queueRoutes([
      { method: 'POST', url: '/api/cases/bulk', response: {
        action: 'transition',
        updated: ['RQB-2026-0347'],
        skipped: [{ case_id: 'RQB-2026-0422', reason: skippedReason }],
        updated_count: 1,
        skipped_count: 1,
      } },
    ]))
    render(<AlertsPage role="analyst" />)

    await screen.findByRole('heading', { name: 'Alert queue' })
    await user.click(screen.getByLabelText('Select all in view'))
    const reviewButton = screen.getByRole('button', { name: 'Review close' })
    expect(reviewButton).toBeDisabled()

    await user.type(screen.getByLabelText('Close rationale'), 'Confirmed false positives')
    expect(reviewButton).toBeEnabled()
    await user.click(reviewButton)

    const review = screen.getByRole('region', { name: 'Confirm closing 2 cases' })
    expect(review).toHaveTextContent('RQB-2026-0347, RQB-2026-0422')
    expect(review).toHaveTextContent('Confirmed false positives')
    expect(screen.getByRole('button', { name: 'Confirm close' })).toHaveFocus()
    expect(fetchMock.mock.calls.some(([url, init]) => url === '/api/cases/bulk' && init?.method === 'POST')).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Confirm close' }))
    const result = await screen.findByRole('alert')
    expect(result).toHaveTextContent('1 case closed with a recorded rationale')
    expect(result).toHaveTextContent('RQB-2026-0422')
    expect(result).toHaveTextContent(skippedReason)

    const call = fetchMock.mock.calls.find(([url, init]) => url === '/api/cases/bulk' && init?.method === 'POST')
    expect(JSON.parse(call[1].body)).toEqual({
      case_ids: ['RQB-2026-0347', 'RQB-2026-0422'],
      action: 'transition',
      status: 'closed',
      reason: 'Confirmed false positives',
    })
    expect(screen.getByLabelText('Select RQB-2026-0422')).toBeChecked()
  })

  it('keeps mutation errors visible after the queue has loaded', async () => {
    const user = userEvent.setup()
    mockJsonFetch(queueRoutes([
      { method: 'POST', url: '/api/cases/bulk', status: 503, response: { detail: 'Triage service unavailable' } },
    ]))
    render(<AlertsPage role="analyst" />)

    await screen.findByRole('heading', { name: 'Alert queue' })
    await user.click(screen.getByLabelText('Select RQB-2026-0347'))
    await user.type(screen.getByLabelText('Owner'), 'Desk 4')
    await user.click(screen.getByRole('button', { name: 'Assign' }))

    const error = await screen.findByRole('alert')
    expect(error).toHaveTextContent('Action not completed')
    expect(error).toHaveTextContent('Triage service unavailable')
    expect(screen.getByText('Al Rashidi Trading FZE')).toBeInTheDocument()
    expect(screen.getByLabelText('Select RQB-2026-0347')).toBeChecked()
  })

  it('clears scoped selection when the queue view changes', async () => {
    const user = userEvent.setup()
    mockJsonFetch(queueRoutes())
    render(<AlertsPage role="analyst" />)

    await screen.findByRole('heading', { name: 'Alert queue' })
    await user.click(screen.getByLabelText('Select RQB-2026-0347'))
    expect(screen.getByRole('region', { name: 'Bulk triage actions' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'high' }))

    expect(screen.queryByRole('region', { name: 'Bulk triage actions' })).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('Selection cleared because the queue view changed')
    expect(screen.getByText('Cedarwood Interiors LLC')).toBeInTheDocument()
  })

  it('filters with canonical workflow statuses from the backend', async () => {
    const user = userEvent.setup()
    const draft = { ...ALERTS[0], workflow_status: 'draft_ready', case_status: 'open', status: 'open' }
    mockJsonFetch([
      { url: '/api/alerts', response: { alerts: [draft, ALERTS[1]] } },
      { url: '/api/triage', response: TRIAGE },
    ])
    render(<AlertsPage role="analyst" />)

    await screen.findByRole('heading', { name: 'Alert queue' })
    expect(screen.queryByText('Al Rashidi Trading FZE')).toBeNull()
    await user.selectOptions(screen.getByLabelText('Status'), 'draft_ready')
    expect(screen.getByText('Al Rashidi Trading FZE')).toBeInTheDocument()
    expect(screen.getByText('Draft ready', { selector: '.status-label' })).toBeInTheDocument()
    expect([...screen.getByLabelText('Status').options].map((option) => option.value)).toEqual([
      'all', 'open', 'investigating', 'draft_ready', 'pending_review', 'changes_requested', 'approved', 'closed',
    ])
  })

  it('hides triage controls from personas that cannot act', async () => {
    mockJsonFetch(queueRoutes())
    render(<AlertsPage role="auditor" />)

    await screen.findByRole('heading', { name: 'Alert queue' })
    expect(screen.queryByLabelText('Select all in view')).toBeNull()
    expect(screen.queryByLabelText('Select RQB-2026-0347')).toBeNull()
  })

  it('offers a rule-admin-only demo reset that reopens the queue', async () => {
    const user = userEvent.setup()
    const fetchMock = mockJsonFetch(queueRoutes([
      { method: 'POST', url: '/api/demo/reset',
        response: { reopened: ['RQB-2026-0347', 'RQB-2026-0357'], reopened_count: 2 } },
    ]))
    render(<AlertsPage role="rule_admin" />)

    await screen.findByRole('heading', { name: 'Alert queue' })
    await user.click(screen.getByRole('button', { name: 'Reset demo' }))

    expect(await screen.findByText(/2 cases reopened to the active queue/)).toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([url, init]) => url === '/api/demo/reset' && init?.method === 'POST')
    expect(call).toBeDefined()
    expect(call[1].headers).toEqual(expect.objectContaining({ 'X-Raqib-Role': 'rule_admin' }))
  })

  it('hides the demo reset from personas without the permission', async () => {
    mockJsonFetch(queueRoutes())
    render(<AlertsPage role="analyst" />)

    await screen.findByRole('heading', { name: 'Alert queue' })
    expect(screen.queryByRole('button', { name: 'Reset demo' })).toBeNull()
  })
})

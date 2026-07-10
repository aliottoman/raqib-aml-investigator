import React from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import IntelligencePage from '../pages/IntelligencePage.jsx'
import { mockJsonFetch } from './mockFetch.js'

const RULE = {
  id: 'CASH-VELOCITY-04',
  name: 'Sub-threshold cash velocity',
  description: 'Detects repeated cash deposits below the reporting threshold.',
  category: 'Structuring',
  severity: 'critical',
  enabled: true,
  parameters: {
    minimum_deposits: 3,
    window_business_days: 10,
  },
  policy_reference: '§4.2',
}

describe('rule administration', () => {
  it('lets a rule administrator simulate edited drawer parameters', async () => {
    const user = userEvent.setup()
    const fetchMock = mockJsonFetch([
      { url: '/api/analytics?period=90d', response: {} },
      { url: '/api/rules', response: { rules: [RULE] } },
      {
        method: 'POST',
        url: '/api/rules/CASH-VELOCITY-04/simulate',
        response: {
          baseline: { alert_count: 12 },
          candidate: { alert_count: 7 },
          delta: { alert_count: -5 },
          summary: 'Candidate parameters reduce alerts without persisting changes.',
        },
      },
    ])
    render(<IntelligencePage role="rule_admin" />)

    expect(await screen.findByRole('heading', { name: 'Analytics & rules' })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Rule administration' }))
    const openRule = screen.getByRole('button', { name: `Open ${RULE.name}` })
    await user.click(openRule)

    const drawer = screen.getByRole('dialog', { name: RULE.name })
    const minimumDeposits = within(drawer).getByRole('spinbutton', { name: /minimum deposits/i })
    expect(minimumDeposits).toBeEnabled()
    await user.clear(minimumDeposits)
    await user.type(minimumDeposits, '5')
    await user.click(within(drawer).getByRole('button', { name: 'Simulate changes' }))

    expect(await within(drawer).findByText('Simulation result · no changes persisted')).toBeInTheDocument()
    expect(within(drawer).getByText('Candidate parameters reduce alerts without persisting changes.')).toBeInTheDocument()
    expect(within(drawer).getByText('7')).toBeInTheDocument()

    const simulationCall = fetchMock.mock.calls.find(([url, init]) => (
      url === '/api/rules/CASH-VELOCITY-04/simulate' && init.method === 'POST'
    ))
    expect(simulationCall).toBeDefined()
    expect(simulationCall[1].headers).toEqual(expect.objectContaining({
      'Content-Type': 'application/json',
      'X-Raqib-Role': 'rule_admin',
    }))
    expect(JSON.parse(simulationCall[1].body)).toEqual({
      parameters: {
        minimum_deposits: 5,
        window_business_days: 10,
      },
    })

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: RULE.name })).not.toBeInTheDocument()
    expect(openRule).toHaveFocus()
  })

  it('lets a rule administrator get an AI suggestion that pre-fills the candidate', async () => {
    const user = userEvent.setup()
    const fetchMock = mockJsonFetch([
      { url: '/api/analytics?period=90d', response: {} },
      { url: '/api/rules', response: { rules: [RULE] } },
      {
        method: 'POST',
        url: '/api/rules/CASH-VELOCITY-04/suggest',
        response: {
          rule_id: 'CASH-VELOCITY-04',
          current_parameters: { minimum_deposits: 3, window_business_days: 10 },
          suggested_parameters: { minimum_deposits: 5 },
          rationale: 'Heuristic tighter (~10%) for the stated smurfing typology.',
          backend: 'heuristic',
        },
      },
    ])
    render(<IntelligencePage role="rule_admin" />)

    await screen.findByRole('heading', { name: 'Analytics & rules' })
    await user.click(screen.getByRole('tab', { name: 'Rule administration' }))
    await user.click(screen.getByRole('button', { name: `Open ${RULE.name}` }))
    const drawer = screen.getByRole('dialog', { name: RULE.name })

    await user.type(within(drawer).getByLabelText('Authoring intent'), 'tighten for smurfing')
    await user.click(within(drawer).getByRole('button', { name: 'Suggest parameters (AI)' }))

    // The rationale surfaces and the suggested value pre-fills the editable field.
    expect(await within(drawer).findByText(/Heuristic tighter/)).toBeInTheDocument()
    expect(within(drawer).getByRole('spinbutton', { name: /minimum deposits/i })).toHaveValue(5)

    const call = fetchMock.mock.calls.find(([url, init]) => (
      url === '/api/rules/CASH-VELOCITY-04/suggest' && init.method === 'POST'
    ))
    expect(JSON.parse(call[1].body)).toEqual({ intent: 'tighten for smurfing' })
  })

  it('hides the AI authoring assist from personas without the permission', async () => {
    const user = userEvent.setup()
    mockJsonFetch([
      { url: '/api/analytics?period=90d', response: {} },
      { url: '/api/rules', response: { rules: [RULE] } },
    ])
    render(<IntelligencePage role="auditor" />)

    await screen.findByRole('heading', { name: 'Analytics & rules' })
    await user.click(screen.getByRole('tab', { name: 'Rule administration' }))
    await user.click(screen.getByRole('button', { name: `Open ${RULE.name}` }))
    const drawer = screen.getByRole('dialog', { name: RULE.name })

    expect(within(drawer).queryByLabelText('Authoring intent')).toBeNull()
    expect(within(drawer).queryByRole('button', { name: 'Suggest parameters (AI)' })).toBeNull()
  })
})

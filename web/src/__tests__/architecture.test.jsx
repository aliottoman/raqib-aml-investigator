import React from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import ArchitecturePage from '../pages/ArchitecturePage.jsx'
import { mockJsonFetch } from './mockFetch.js'

describe('architecture modes', () => {
  it('switches from the current implementation to the target OCI blueprint', async () => {
    const user = userEvent.setup()
    mockJsonFetch([{ url: '/api/architecture', response: {} }])
    render(<ArchitecturePage role="auditor" health={{ live_available: false }} />)

    expect(await screen.findByRole('heading', { name: 'Logical architecture' })).toBeInTheDocument()
    expect(screen.getByText('Investigation workbench')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Current build' })).toHaveClass('active')
    expect(screen.getByText('Adapter / contract tested')).toBeInTheDocument()
    expect(screen.getAllByText('Live-validated snapshot').length).toBeGreaterThan(0)
    expect(screen.queryByText('encrypted at rest')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Managed policy retrieval adapter/ }))

    const detail = screen.getByRole('complementary', { name: 'Managed policy retrieval adapter details' })
    expect(within(detail).getByText('Adapter / contract tested')).toBeInTheDocument()
    expect(within(detail).getByText(/No live managed-retrieval validation is recorded/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Target OCI' }))

    expect(screen.getByRole('heading', { name: 'OCI deployment architecture' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Workforce identity/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Target OCI' })).toHaveClass('active')
    expect(screen.getAllByText('Target integration').length).toBeGreaterThan(0)
  })
})

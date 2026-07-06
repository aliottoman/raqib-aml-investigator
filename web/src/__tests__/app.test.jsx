import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../App.jsx'
import { mockJsonFetch } from './mockFetch.js'

describe('role personas', () => {
  it('switches to the auditor persona and keeps screening read-only', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/alerts')
    const fetchMock = mockJsonFetch([
      { url: '/api/health', response: { live_available: false } },
      { url: '/api/session', response: { mode: 'recorded' } },
      { url: '/api/alerts', response: { alerts: [] } },
    ])
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Alert queue' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run screening' })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: /Viewing as\s*Analyst/i }))
    await user.click(screen.getByRole('option', { name: /Independent Auditor/i }))

    expect(await screen.findByRole('button', { name: /Viewing as\s*Auditor/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run screening' })).toBeDisabled()
    expect(screen.getByRole('note')).toHaveTextContent('Screening is analyst-controlled')
    expect(window.localStorage.getItem('raqib-role')).toBe('auditor')
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/alerts', expect.objectContaining({
        headers: expect.objectContaining({ 'X-Raqib-Role': 'auditor' }),
      }))
    })
  })
})

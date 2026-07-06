import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Link, useRoute } from '../router.jsx'

function RouterProbe() {
  const path = useRoute()
  return (
    <>
      <Link to="/cases">Cases</Link>
      <output aria-label="Current route">{path}</output>
    </>
  )
}

describe('client-side routing', () => {
  it('updates the route when a Link is activated', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/overview')
    render(<RouterProbe />)

    await user.click(screen.getByRole('link', { name: 'Cases' }))

    expect(screen.getByLabelText('Current route')).toHaveTextContent('/cases')
    expect(window.location.pathname).toBe('/cases')
  })
})

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
})

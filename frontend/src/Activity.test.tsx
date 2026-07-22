import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Activity } from './Activity'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Activity', () => {
  it('renders worker events with their job and message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          json: () =>
            Promise.resolve([
              {
                id: 1,
                created_at: '2026-07-22T10:00:00Z',
                job: 'resolution',
                type: 'resolved',
                message: "Resolved 'A — B'",
                album_id: 7,
              },
            ]),
        }),
      ),
    )
    const { container } = render(<Activity />)
    await screen.findByText("Resolved 'A — B'")
    expect(container.textContent).toContain('resolution')
  })

  it('shows an empty state before any events', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ json: () => Promise.resolve([]) })),
    )
    render(<Activity />)
    expect(await screen.findByText(/No worker activity/)).toBeTruthy()
  })
})

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SpotifyStatus } from './SpotifyStatus'

function mockStatus(body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ json: () => Promise.resolve(body) })),
  )
}

afterEach(() => {
  cleanup() // globals:false, so RTL's auto-cleanup isn't registered
  vi.unstubAllGlobals()
})

describe('SpotifyStatus', () => {
  it('offers connect when disconnected', async () => {
    mockStatus({ connected: false, authorized_at: null, reauth_in_days: null, reauth_due: true })
    render(<SpotifyStatus />)
    const link = await screen.findByRole('link')
    expect(link.getAttribute('href')).toBe('/auth/spotify/login')
    expect(link.textContent).toContain('Connect')
  })

  it('shows the reauth countdown when connected', async () => {
    mockStatus({
      connected: true,
      authorized_at: '2026-04-01T00:00:00Z',
      reauth_in_days: 83,
      reauth_due: false,
    })
    const { container } = render(<SpotifyStatus />)
    await screen.findByText(/connected/)
    expect(container.textContent).toContain('reauth in 83d')
    expect(screen.queryByRole('link')).toBeNull()
  })
})

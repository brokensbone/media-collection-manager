import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Releases } from './Releases'

function mockApi(items: unknown) {
  const fetchMock = vi.fn((_url: string, opts?: { method?: string }) =>
    opts?.method === 'POST'
      ? Promise.resolve({ ok: true })
      : Promise.resolve({ json: () => Promise.resolve(items) }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Releases', () => {
  it('lists suggested releases', async () => {
    mockApi([{ id: 1, artist: 'The Band', title: 'New One', has_art: false }])
    render(<Releases />)
    expect(await screen.findByText('New One')).toBeTruthy()
  })

  it('links the cover to the album on Spotify in a new tab', async () => {
    mockApi([{ id: 1, artist: 'The Band', title: 'New One', has_art: true, spotify_id: 'spot9' }])
    const { container } = render(<Releases />)
    await screen.findByText('New One')
    const link = container.querySelector('a') as HTMLAnchorElement
    expect(link.href).toContain('open.spotify.com/album/spot9')
    expect(link.target).toBe('_blank')
  })

  it('want: POSTs and removes the row', async () => {
    const fetchMock = mockApi([{ id: 5, artist: 'B', title: 'Only', has_art: false }])
    render(<Releases />)
    await screen.findByText('Only')
    fireEvent.click(screen.getByRole('button', { name: 'Want' }))
    await screen.findByText(/No new releases/)
    const posted = fetchMock.mock.calls.find((c) => c[1]?.method === 'POST')
    expect(posted?.[0]).toBe('/albums/5/want')
  })
})

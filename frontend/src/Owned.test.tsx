import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Owned } from './Owned'

function mockOwned(body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ json: () => Promise.resolve(body) })),
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Owned', () => {
  it('lists the whole library, flagging albums also on Spotify', async () => {
    mockOwned([
      {
        beets_id: 'b1',
        artist: 'A',
        title: 'Matched',
        album_id: 1,
        has_art: true,
        on_spotify: true,
        spotify_id: 'spot1',
      },
      {
        beets_id: 'b2',
        artist: 'B',
        title: 'Only In Beets',
        album_id: null,
        has_art: false,
        on_spotify: false,
        spotify_id: null,
      },
    ])
    const { container } = render(<Owned />)
    await screen.findByText('Matched')
    expect(container.textContent).toContain('Only In Beets')
    expect(container.textContent).toContain('on Spotify')
  })

  it('links a matched cover to the album on Spotify in a new tab', async () => {
    mockOwned([
      {
        beets_id: 'b1',
        artist: 'A',
        title: 'Matched',
        album_id: 1,
        has_art: true,
        on_spotify: true,
        spotify_id: 'spot1',
      },
    ])
    const { container } = render(<Owned />)
    await screen.findByText('Matched')
    const link = container.querySelector('a') as HTMLAnchorElement
    expect(link.href).toContain('open.spotify.com/album/spot1')
    expect(link.target).toBe('_blank')
  })

  it('shows an empty state', async () => {
    mockOwned([])
    render(<Owned />)
    expect(await screen.findByText(/Nothing here/)).toBeTruthy()
  })
})

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
  window.location.hash = ''
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

  it('gives each row a shareable permalink to that beets entry', async () => {
    mockOwned([
      {
        beets_id: 'b7',
        artist: 'A',
        title: 'Dupe',
        album_id: null,
        has_art: false,
        on_spotify: false,
        spotify_id: null,
      },
    ])
    render(<Owned />)
    await screen.findByText('Dupe')
    expect(screen.getByTitle('Link to this album').getAttribute('href')).toBe('#owned?sel=b7')
  })

  it('highlights the row named by #owned?sel= in the URL', async () => {
    window.location.hash = 'owned?sel=b7'
    mockOwned([
      {
        beets_id: 'b7',
        artist: 'A',
        title: 'Dupe',
        album_id: null,
        has_art: false,
        on_spotify: false,
        spotify_id: null,
      },
      {
        beets_id: 'b8',
        artist: 'A',
        title: 'Other',
        album_id: null,
        has_art: false,
        on_spotify: false,
        spotify_id: null,
      },
    ])
    const { container } = render(<Owned />)
    await screen.findByText('Dupe')
    expect(container.querySelector('#owned-b7')?.className).toContain('linked')
    expect(container.querySelector('#owned-b8')?.className ?? '').not.toContain('linked')
  })
})

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Acquire } from './Acquire'

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

describe('Acquire', () => {
  it('shows a Bandcamp buy link per item', async () => {
    mockApi([
      {
        id: 1,
        artist: 'A',
        title: 'T1',
        has_art: false,
        bandcamp_url: 'https://bandcamp.com/search?q=A+T1',
      },
    ])
    render(<Acquire />)
    const link = await screen.findByRole('link', { name: 'Buy on Bandcamp' })
    expect(link.getAttribute('href')).toBe('https://bandcamp.com/search?q=A+T1')
  })

  it('marks ordered: POSTs and removes the row', async () => {
    const fetchMock = mockApi([
      { id: 9, artist: 'A', title: 'Only', has_art: false, bandcamp_url: 'https://x' },
    ])
    render(<Acquire />)
    await screen.findByText('Only')
    fireEvent.click(screen.getByRole('button', { name: 'Mark ordered' }))
    await screen.findByText(/Nothing to acquire/)
    const posted = fetchMock.mock.calls.find((c) => c[1]?.method === 'POST')
    expect(posted?.[0]).toBe('/albums/9/order')
  })
})

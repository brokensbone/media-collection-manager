import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Acquire } from './Acquire'

function mockApi(items: unknown, candidates: unknown = []) {
  const fetchMock = vi.fn((url: string, opts?: { method?: string }) => {
    if (opts?.method === 'POST') return Promise.resolve({ ok: true })
    if (url.includes('/link-candidates'))
      return Promise.resolve({ json: () => Promise.resolve(candidates) })
    return Promise.resolve({ json: () => Promise.resolve(items) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function item(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    artist: 'A',
    title: 'T1',
    has_art: false,
    bandcamp_url: 'https://bandcamp.com/search?q=A+T1',
    possibly_owned: false,
    owned_hint: null,
    ...over,
  }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Acquire', () => {
  it('shows a Bandcamp buy link per item', async () => {
    mockApi([item()])
    render(<Acquire />)
    const link = await screen.findByRole('link', { name: 'Bandcamp' })
    expect(link.getAttribute('href')).toBe('https://bandcamp.com/search?q=A+T1')
  })

  it('filters rows by the query across artist and title', async () => {
    mockApi([
      item({ id: 1, artist: 'Porridge Radio', title: 'Every Bad' }),
      item({ id: 2, artist: 'Burial', title: 'Untrue' }),
    ])
    render(<Acquire query="porri ev" />)
    expect(await screen.findByText('Every Bad')).toBeTruthy()
    expect(screen.queryByText('Untrue')).toBeNull()
  })

  it('flags a possibly-owned want with its hint', async () => {
    mockApi([item({ possibly_owned: true, owned_hint: 'A — T1 (Deluxe)' })])
    render(<Acquire />)
    expect(await screen.findByText(/possibly owned: A — T1 \(Deluxe\)/)).toBeTruthy()
  })

  it('marks ordered: POSTs and removes the row', async () => {
    const fetchMock = mockApi([item({ id: 9, title: 'Only' })])
    render(<Acquire />)
    await screen.findByText('Only')
    fireEvent.click(screen.getByRole('button', { name: 'Mark ordered' }))
    await screen.findByText(/Nothing to acquire/)
    const posted = fetchMock.mock.calls.find((c) => c[1]?.method === 'POST')
    expect(posted?.[0]).toBe('/albums/9/order')
  })

  it('links to a library candidate: fetches candidates then POSTs the chosen beets_id', async () => {
    const fetchMock = mockApi(
      [item({ id: 9, title: 'Only' })],
      [
        {
          beets_id: 'b7',
          artist: 'A',
          title: 'Only (Remaster)',
          has_release_group: true,
          score: 0.9,
        },
      ],
    )
    render(<Acquire />)
    await screen.findByText('Only')
    fireEvent.click(screen.getByRole('button', { name: 'Mark owned…' }))
    const link = await screen.findByRole('button', { name: /Link: A — Only \(Remaster\)/ })
    fireEvent.click(link)
    await screen.findByText(/Nothing to acquire/)

    const posted = fetchMock.mock.calls.find((c) => c[1]?.method === 'POST')
    expect(posted?.[0]).toBe('/albums/9/mark-owned')
    expect(JSON.parse((posted?.[1] as { body: string }).body)).toEqual({ beets_id: 'b7' })
  })

  it('marks owned with no link', async () => {
    const fetchMock = mockApi([item({ id: 9, title: 'Only' })])
    render(<Acquire />)
    await screen.findByText('Only')
    fireEvent.click(screen.getByRole('button', { name: 'Mark owned…' }))
    const noLink = await screen.findByRole('button', { name: 'Mark owned (no link)' })
    fireEvent.click(noLink)
    await screen.findByText(/Nothing to acquire/)

    const posted = fetchMock.mock.calls.find((c) => c[1]?.method === 'POST')
    expect(posted?.[0]).toBe('/albums/9/mark-owned')
    expect(JSON.parse((posted?.[1] as { body: string }).body)).toEqual({ beets_id: null })
  })
})

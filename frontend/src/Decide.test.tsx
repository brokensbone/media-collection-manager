import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Decide } from './Decide'

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

describe('Decide', () => {
  it('lists items with their reason', async () => {
    mockApi([{ id: 1, artist: 'A', title: 'T1', reason: '30d', has_art: false }])
    render(<Decide />)
    expect(await screen.findByText('T1')).toBeTruthy()
    expect(screen.getByText('30d')).toBeTruthy()
  })

  it('keeps an item: POSTs and removes it from the queue', async () => {
    const fetchMock = mockApi([{ id: 7, artist: 'A', title: 'Only', reason: 'r', has_art: false }])
    render(<Decide />)
    await screen.findByText('Only')
    fireEvent.click(screen.getByRole('button', { name: 'Keep' }))
    await screen.findByText(/Nothing to judge/)
    const posted = fetchMock.mock.calls.find((c) => c[1]?.method === 'POST')
    expect(posted?.[0]).toBe('/albums/7/keep')
  })
})

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Imports } from './Imports'

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

describe('Imports', () => {
  it('shows the matched want and a no-match label', async () => {
    mockApi([
      { id: 1, name: 'Burial-Untrue', matched_album_id: 5, matched: 'Burial — Untrue' },
      { id: 2, name: 'Mystery', matched_album_id: null, matched: null },
    ])
    render(<Imports />)
    expect(await screen.findByText('Burial — Untrue')).toBeTruthy()
    expect(screen.getByText('no match')).toBeTruthy()
  })

  it('imports: POSTs and removes the row', async () => {
    const fetchMock = mockApi([{ id: 9, name: 'Only', matched_album_id: null, matched: null }])
    render(<Imports />)
    await screen.findByText('Only')
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))
    await screen.findByText(/No downloads to import/)
    const posted = fetchMock.mock.calls.find((c) => c[1]?.method === 'POST')
    expect(posted?.[0]).toBe('/imports/9/import')
  })
})

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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

function item(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    source: 'watchdir',
    name: 'Album.zip',
    state: 'detected',
    matched_album_id: null,
    matched: null,
    ...over,
  }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Imports', () => {
  it('shows the source, matched want and a no-match label', async () => {
    mockApi([
      item({ id: 1, source: 'transmission', name: 'Burial-Untrue', matched: 'Burial — Untrue' }),
      item({ id: 2, name: 'Mystery' }),
    ])
    render(<Imports />)
    expect(await screen.findByText('Burial — Untrue')).toBeTruthy()
    expect(screen.getByText('transmission')).toBeTruthy()
    expect(screen.getByText('no match')).toBeTruthy()
  })

  it('import enqueues and the row persists showing queued, not vanishing', async () => {
    const fetchMock = mockApi([item({ id: 9, name: 'Only' })])
    render(<Imports />)
    await screen.findByText('Only')
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))

    const posted = fetchMock.mock.calls.find((c) => c[1]?.method === 'POST')
    expect(posted?.[0]).toBe('/imports/9/import')
    // row stays, now showing queued status
    expect(screen.getByText('Only')).toBeTruthy()
    await waitFor(() => expect(screen.getByText('queued')).toBeTruthy())
  })

  it('shows a Retry for a failed import', async () => {
    mockApi([item({ id: 3, name: 'Bad.zip', state: 'failed' })])
    render(<Imports />)
    expect(await screen.findByText('failed')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy()
  })

  it('flags a match that is already owned', async () => {
    mockApi([
      item({ id: 5, name: 'Dup', matched: 'Burial — Untrue', matched_owned: true }),
      item({ id: 6, name: 'New', matched: 'Someone — Thing', matched_owned: false }),
    ])
    render(<Imports />)
    expect(await screen.findByText('owned')).toBeTruthy()
    // only the owned match is flagged
    expect(screen.getAllByText('owned')).toHaveLength(1)
  })

  it('discards a detected row via DELETE and drops it from the list', async () => {
    const fetchMock = mockApi([item({ id: 7, name: 'Unwanted' })])
    render(<Imports />)
    await screen.findByText('Unwanted')
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }))

    const deleted = fetchMock.mock.calls.find((c) => c[1]?.method === 'DELETE')
    expect(deleted?.[0]).toBe('/imports/7')
    expect(screen.queryByText('Unwanted')).toBeNull()
  })

  it('shows the active import and a batch progress summary', async () => {
    mockApi([
      item({ id: 1, name: 'A', state: 'imported' }),
      item({ id: 2, name: 'B', state: 'importing' }),
      item({ id: 3, name: 'C', state: 'queued' }),
    ])
    render(<Imports />)
    expect(await screen.findByText('importing…')).toBeTruthy()
    expect(screen.getByText('queued')).toBeTruthy()
    // 1 done, so it's on the 2nd of 3, with 1 still queued
    expect(screen.getByText(/Importing 2 of 3/)).toBeTruthy()
    expect(screen.getByText(/1 queued/)).toBeTruthy()
  })

  it('shows imported status without an action', async () => {
    mockApi([item({ id: 4, name: 'Done.zip', state: 'imported' })])
    render(<Imports />)
    expect(await screen.findByText('imported ✓')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })
})

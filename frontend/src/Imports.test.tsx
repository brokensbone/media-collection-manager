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

function mockApiSequence(responses: unknown[]) {
  let get = 0
  const fetchMock = vi.fn((_url: string, opts?: { method?: string }) =>
    opts?.method === 'POST'
      ? Promise.resolve({ ok: true })
      : Promise.resolve({
          json: () => Promise.resolve(responses[get++] ?? responses[responses.length - 1]),
        }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function item(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    source: 'watchdir',
    name: 'Album.zip',
    media_kind: 'music',
    import_target: 'beets',
    classification_detail: null,
    destination_path: null,
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
      item({ id: 2, name: 'Mystery', media_kind: 'film', destination_path: '/film/Mystery' }),
    ])
    render(<Imports />)
    expect(await screen.findByText('Burial — Untrue')).toBeTruthy()
    expect(screen.getByText('transmission')).toBeTruthy()
    expect(screen.getByText('no match')).toBeTruthy()
    expect(screen.getByText('/film/Mystery')).toBeTruthy()
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

  it('keeps a queued row queued when a follow-up poll still reports it detected', async () => {
    // The race: the post-Import refresh (and background polls) can still return the pre-click
    // detected row; the optimistic queued state must stick, not flash back to the Import button.
    mockApiSequence([
      [item({ id: 9, name: 'Only' })], // initial poll: detected
      [item({ id: 9, name: 'Only' })], // post-import refresh: still detected (stale)
      [item({ id: 9, name: 'Only' })],
    ])
    render(<Imports />)
    await screen.findByText('Only')
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))
    await waitFor(() => expect(screen.getByText('queued')).toBeTruthy())
    expect(screen.queryByRole('button', { name: 'Import' })).toBeNull()
  })

  it('keeps a discarded row gone when a follow-up poll still returns it', async () => {
    mockApiSequence([
      [item({ id: 7, name: 'Unwanted' })],
      [item({ id: 7, name: 'Unwanted' })], // stale refresh still lists it
      [item({ id: 7, name: 'Unwanted' })],
    ])
    render(<Imports />)
    await screen.findByText('Unwanted')
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }))
    await waitFor(() => expect(screen.queryByText('Unwanted')).toBeNull())
    expect(screen.queryByText('Unwanted')).toBeNull()
  })

  it('keeps a row in place when Retry changes its state (no jump)', async () => {
    // Retrying a failed row flips it to queued; the server then sorts active rows to the top.
    // The list must keep the row where it is rather than jumping it up under the cursor.
    const a = item({ id: 1, name: 'Aaa', state: 'detected' })
    const z = item({ id: 2, name: 'Zzz', state: 'failed' })
    mockApiSequence([
      [a, z], // initial order: Aaa, then Zzz
      [{ ...z, state: 'queued' }, a], // after retry: server re-sorts queued Zzz to the top
      [{ ...z, state: 'queued' }, a],
    ])
    const { container } = render(<Imports />)
    await screen.findByText('Zzz')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(screen.getByText('queued')).toBeTruthy())
    const text = container.textContent ?? ''
    expect(text.indexOf('Aaa')).toBeLessThan(text.indexOf('Zzz')) // order unchanged
  })

  it('scans the watch folder and refreshes newly detected rows', async () => {
    const fetchMock = mockApiSequence([[], [item({ id: 8, name: 'Dropped Folder' })]])
    render(<Imports />)
    expect(await screen.findByText('No downloads to import.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Scan watch folder' }))

    const posted = fetchMock.mock.calls.find((c) => c[0] === '/imports/scan')
    expect(posted?.[1]?.method).toBe('POST')
    expect(await screen.findByText('Dropped Folder')).toBeTruthy()
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

  it('summarises only active work, ignoring already-imported history', async () => {
    mockApi([
      item({ id: 1, name: 'A', state: 'imported' }), // history, must not inflate the summary
      item({ id: 2, name: 'B', state: 'importing' }),
      item({ id: 3, name: 'C', state: 'queued' }),
    ])
    render(<Imports />)
    // summary reflects the active batch only: one importing, one queued
    expect(await screen.findByText('Importing… · 1 queued')).toBeTruthy()
  })

  it('hides the progress summary when nothing is active', async () => {
    mockApi([item({ id: 1, name: 'A', state: 'imported' })])
    render(<Imports />)
    await screen.findByText('A')
    expect(screen.queryByText(/Importing/)).toBeNull()
    expect(screen.queryByText(/queued/)).toBeNull()
  })

  it('shows an already-in-library skip without actions', async () => {
    mockApi([item({ id: 4, name: 'Dup.zip', state: 'skipped' })])
    render(<Imports />)
    expect(await screen.findByText('already in library')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Import' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Discard' })).toBeNull()
  })

  it('shows imported status without an action', async () => {
    mockApi([item({ id: 4, name: 'Done.zip', state: 'imported' })])
    render(<Imports />)
    expect(await screen.findByText('imported ✓')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Import' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Discard' })).toBeNull()
  })

  it('shows blocked review-only rows without an Import action', async () => {
    mockApi([
      item({
        id: 10,
        name: 'Mystery Pack',
        media_kind: 'unknown',
        import_target: 'review',
        classification_detail: 'Video files found, but the title or type is ambiguous.',
      }),
    ])
    render(<Imports />)
    expect(await screen.findByText('needs review')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Import' })).toBeNull()
  })

  it('filters the list by type and back to all', async () => {
    mockApi([
      item({ id: 1, name: 'A Song' }), // music (beets)
      item({ id: 2, name: 'The Show S01', import_target: 'tv', media_kind: 'tv' }),
      item({ id: 3, name: 'A Film', import_target: 'film', media_kind: 'film' }),
    ])
    render(<Imports />)
    await screen.findByText('A Song')
    // all three rows visible before filtering
    expect(screen.getByText('The Show S01')).toBeTruthy()
    expect(screen.getByText('A Film')).toBeTruthy()

    // click the TV filter tab (accessible name includes its count, e.g. "1 TV")
    fireEvent.click(screen.getByRole('button', { name: /\bTV$/ }))
    await waitFor(() => expect(screen.queryByText('A Song')).toBeNull())
    expect(screen.getByText('The Show S01')).toBeTruthy()
    expect(screen.queryByText('A Film')).toBeNull()

    // All brings everything back
    fireEvent.click(screen.getByRole('button', { name: /\ball$/ }))
    await waitFor(() => expect(screen.getByText('A Song')).toBeTruthy())
    expect(screen.getByText('A Film')).toBeTruthy()
  })

  it('groups a review-target row under Review, not its media kind', async () => {
    mockApi([
      item({ id: 1, name: 'Clean Film', import_target: 'film', media_kind: 'film' }),
      // a mixed-season TV pack routed to review — belongs under Review, not TV
      item({ id: 2, name: 'Mixed Pack', import_target: 'review', media_kind: 'tv' }),
    ])
    render(<Imports />)
    await screen.findByText('Clean Film')
    fireEvent.click(screen.getByRole('button', { name: /\bReview$/ }))
    await waitFor(() => expect(screen.queryByText('Clean Film')).toBeNull())
    expect(screen.getByText('Mixed Pack')).toBeTruthy()
  })

  it('shows no type filter when only one type is present', async () => {
    mockApi([item({ id: 1, name: 'A Song' }), item({ id: 2, name: 'Another Song' })])
    render(<Imports />)
    await screen.findByText('A Song')
    expect(screen.queryByRole('button', { name: /Music$/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /\ball$/ })).toBeNull()
  })
})

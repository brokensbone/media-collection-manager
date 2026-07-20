import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Transmission } from './Transmission'

function mockApi(torrents: unknown, testReport?: unknown) {
  const fetchMock = vi.fn((url: string, opts?: { method?: string }) => {
    if (url === '/transmission/test' && opts?.method === 'POST') {
      return Promise.resolve({ json: () => Promise.resolve(testReport) })
    }
    return Promise.resolve({ json: () => Promise.resolve(torrents) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Transmission', () => {
  it('lists torrents seen, including non-audio ones', async () => {
    mockApi([
      { id: 1, name: 'An Album', state: 'detected', matched: 'X — Y', has_audio: true },
      { id: 2, name: 'A Movie', state: 'dismissed', matched: null, has_audio: false },
    ])
    render(<Transmission />)
    expect(await screen.findByText('An Album')).toBeTruthy()
    expect(screen.getByText('A Movie')).toBeTruthy()
    expect(screen.getByText('non-audio')).toBeTruthy()
  })

  it('runs a connection test and shows API and SSH results', async () => {
    const fetchMock = mockApi([], {
      api: { ok: true, detail: 'Connected to the Transmission RPC.' },
      ssh: { ok: false, detail: 'Permission denied (publickey).' },
    })
    render(<Transmission />)
    await screen.findByText(/No torrents seen yet/)
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    const posted = fetchMock.mock.calls.find((c) => c[1]?.method === 'POST')
    expect(posted?.[0]).toBe('/transmission/test')
    await waitFor(() => expect(screen.getByText(/Connected to the Transmission RPC/)).toBeTruthy())
    expect(screen.getByText(/Permission denied/)).toBeTruthy()
  })
})

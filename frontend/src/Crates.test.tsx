import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Crates } from './Crates'

function mockCrates(box: unknown) {
  const fetchMock = vi.fn((_url: string, opts?: { method?: string; body?: string }) =>
    opts?.method
      ? Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      : Promise.resolve({ json: () => Promise.resolve(box) }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function boxView(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    name: 'Collection',
    parent_id: null,
    breadcrumb: [{ id: 1, name: 'Collection' }],
    children: [{ id: 2, name: 'Electronic', loose_count: 3, total_count: 12 }],
    records: [{ beets_id: 'b1', artist: 'Burial', title: 'Untrue', year: 2007, media: 'CD' }],
    loose_count: 1,
    total_count: 13,
    soft_cap: 50,
    over_cap: false,
    ...over,
  }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.location.hash = ''
})

describe('Crates', () => {
  it('shows the box, its sub-boxes with counts, and loose records', async () => {
    mockCrates(boxView())
    render(<Crates />)
    expect(await screen.findByRole('heading', { name: 'Collection' })).toBeTruthy()
    expect(screen.getByText('Electronic')).toBeTruthy()
    expect(screen.getByText('12')).toBeTruthy() // sub-box total count
    expect(screen.getByText('Burial')).toBeTruthy()
    expect(screen.getByText('Untrue')).toBeTruthy()
  })

  it('reveals move actions when a record is selected; root cannot kick up', async () => {
    mockCrates(boxView())
    render(<Crates />)
    await screen.findByText('Burial')
    fireEvent.click(screen.getByLabelText('Select Burial — Untrue'))
    expect(screen.getByText('1 selected')).toBeTruthy()
    const kick = screen.getByRole('button', { name: 'Kick up' }) as HTMLButtonElement
    expect(kick.disabled).toBe(true) // root has no parent
  })

  it('creates a sub-box via POST /crates/box under the current box', async () => {
    const fetchMock = mockCrates(boxView())
    render(<Crates />)
    await screen.findByRole('heading', { name: 'Collection' })
    fireEvent.change(screen.getByPlaceholderText('new sub-box…'), { target: { value: 'Jazz' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => {
      const posted = fetchMock.mock.calls.find(
        (c) => c[0] === '/crates/box' && c[1]?.method === 'POST',
      )
      expect(posted).toBeTruthy()
      expect(String(posted?.[1]?.body)).toContain('Jazz')
    })
  })

  it('shows a cap-meter over-cap nudge when the loose pile exceeds the soft cap', async () => {
    mockCrates(boxView({ loose_count: 60, soft_cap: 50, over_cap: true }))
    render(<Crates />)
    expect(await screen.findByText(/consider splitting/)).toBeTruthy()
  })

  it('previews split suggestions and applies the chosen one', async () => {
    const suggestions = [
      {
        key: 'decade',
        label: 'Decade',
        groups: [
          { name: '2000s', count: 24 },
          { name: '2010s', count: 21 },
        ],
        covers: 45,
        leaves: 12,
      },
    ]
    const fetchMock = vi.fn((url: string, opts?: { method?: string; body?: string }) => {
      if (opts?.method) return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      const body = url.endsWith('/split-suggestions') ? suggestions : boxView()
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<Crates />)
    await screen.findByRole('heading', { name: 'Collection' })
    fireEvent.click(screen.getByRole('button', { name: '✨ Suggest a split' }))

    expect(await screen.findByText(/2000s \(24\)/)).toBeTruthy()
    expect(screen.getByText(/leaves 12/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))
    await waitFor(() => {
      const posted = fetchMock.mock.calls.find(
        (c) => c[0] === '/crates/box/1/split' && c[1]?.method === 'POST',
      )
      expect(posted).toBeTruthy()
      expect(String(posted?.[1]?.body)).toContain('decade')
    })
  })

  it('reports when no clean split is found', async () => {
    const fetchMock = vi.fn((url: string, opts?: { method?: string }) => {
      if (opts?.method) return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      const body = url.endsWith('/split-suggestions') ? [] : boxView()
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<Crates />)
    await screen.findByRole('heading', { name: 'Collection' })
    fireEvent.click(screen.getByRole('button', { name: '✨ Suggest a split' }))
    expect(await screen.findByText('No clean split found — file by hand.')).toBeTruthy()
  })
})

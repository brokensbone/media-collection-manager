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
})

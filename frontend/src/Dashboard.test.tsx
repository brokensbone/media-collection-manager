import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Dashboard } from './Dashboard'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Dashboard', () => {
  it('shows the worklist counts', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          json: () =>
            Promise.resolve({
              releases: 1,
              decide: 3,
              acquire: 12,
              import: 5,
              owned: 40,
              dismissed: 2,
            }),
        }),
      ),
    )
    const { container } = render(<Dashboard />)
    expect(await screen.findByText('decide')).toBeTruthy()
    expect(container.textContent).toContain('3 decide')
    expect(container.textContent).toContain('12 acquire')
    expect(container.textContent).toContain('5 import')
  })

  it('refetches its counts when refreshKey changes', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        json: () =>
          Promise.resolve({
            releases: 0,
            decide: 1,
            acquire: 0,
            import: 0,
            owned: 0,
            dismissed: 0,
          }),
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = render(<Dashboard refreshKey={0} />)
    await screen.findByText('decide')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    rerender(<Dashboard refreshKey={1} />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })
})

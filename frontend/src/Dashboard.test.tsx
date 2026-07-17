import { cleanup, render, screen } from '@testing-library/react'
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
})

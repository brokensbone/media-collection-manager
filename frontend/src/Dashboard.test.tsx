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
            Promise.resolve({ decide: 3, acquire: 12, owned: 40, dismissed: 2, saved: 9 }),
        }),
      ),
    )
    const { container } = render(<Dashboard />)
    expect(await screen.findByText('to judge')).toBeTruthy()
    expect(container.textContent).toContain('3')
    expect(container.textContent).toContain('12 to buy')
  })
})

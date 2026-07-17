import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ json: () => Promise.resolve([]) })),
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('renders the app name', () => {
    stubFetch()
    render(<App />)
    expect(screen.getByText('wantlist')).toBeTruthy()
  })

  it('toggles to the guide from the top bar and back', () => {
    stubFetch()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Guide' }))
    expect(screen.getByRole('heading', { name: 'How wantlist works' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Dashboard' }))
    expect(screen.queryByRole('heading', { name: 'How wantlist works' })).toBeNull()
  })
})

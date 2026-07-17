import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { Guide } from './Guide'

afterEach(cleanup)

describe('Guide', () => {
  it('walks through each worklist', () => {
    render(<Guide />)
    for (const section of ['Decide', 'Acquire', 'Releases', 'Import']) {
      expect(screen.getByRole('heading', { name: section })).toBeTruthy()
    }
  })

  it('explains the loop and that it is not a recommender', () => {
    render(<Guide />)
    expect(screen.getByText(/saved → decide → wanted → acquire → owned/)).toBeTruthy()
    expect(screen.getByText(/not a recommender/)).toBeTruthy()
  })

  it('covers reconnecting to Spotify and why it matters', () => {
    render(<Guide />)
    expect(screen.getByRole('heading', { name: /Staying connected to Spotify/ })).toBeTruthy()
    expect(screen.getByText(/every worklist quietly stops filling/)).toBeTruthy()
  })
})

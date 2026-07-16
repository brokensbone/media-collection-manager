import { useCallback, useEffect, useState } from 'react'

type Item = { id: number; artist: string; title: string; has_art: boolean; bandcamp_url: string }
type Action = 'order' | 'mark-owned'

export function Acquire() {
  const [items, setItems] = useState<Item[] | null>(null)

  useEffect(() => {
    fetch('/acquire')
      .then((r) => r.json())
      .then(setItems)
      .catch(() => setItems([]))
  }, [])

  const act = useCallback((id: number, action: Action) => {
    setItems((list) => {
      if (!list) return list
      fetch(`/albums/${id}/${action}`, { method: 'POST' })
      return list.filter((it) => it.id !== id)
    })
  }, [])

  if (!items) return <p>Loading…</p>
  if (items.length === 0) return <p>Nothing to acquire.</p>

  return (
    <table>
      <tbody>
        {items.map((it) => (
          <tr key={it.id}>
            <td>{it.artist}</td>
            <td>{it.title}</td>
            <td>
              <a href={it.bandcamp_url} target="_blank" rel="noreferrer">
                Buy on Bandcamp
              </a>
            </td>
            <td>
              <button type="button" onClick={() => act(it.id, 'order')}>
                Mark ordered
              </button>
              <button type="button" onClick={() => act(it.id, 'mark-owned')}>
                Mark owned
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

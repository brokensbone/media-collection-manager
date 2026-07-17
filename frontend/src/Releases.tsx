import { useCallback, useEffect, useState } from 'react'
import { Cover } from './Cover'

type Item = { id: number; artist: string; title: string; has_art: boolean }
type Action = 'save' | 'want' | 'dismiss'

export function Releases() {
  const [items, setItems] = useState<Item[] | null>(null)

  useEffect(() => {
    fetch('/releases')
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
  if (items.length === 0) return <p>No new releases.</p>

  return (
    <table>
      <tbody>
        {items.map((it) => (
          <tr key={it.id}>
            <Cover id={it.id} hasArt={it.has_art} />
            <td>{it.artist}</td>
            <td>{it.title}</td>
            <td className="nowrap">
              <button type="button" onClick={() => act(it.id, 'save')}>
                Save
              </button>
              <button type="button" onClick={() => act(it.id, 'want')}>
                Want
              </button>
              <button type="button" onClick={() => act(it.id, 'dismiss')}>
                Dismiss
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

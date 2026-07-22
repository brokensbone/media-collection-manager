import { useCallback, useEffect, useState } from 'react'
import { Cover } from './Cover'
import { matchesQuery } from './filter'

type Item = {
  id: number
  artist: string
  title: string
  has_art: boolean
  spotify_id: string | null
}
type Action = 'save' | 'want' | 'dismiss'

export function Releases({ onChange, query = '' }: { onChange?: () => void; query?: string }) {
  const [items, setItems] = useState<Item[] | null>(null)

  useEffect(() => {
    fetch('/releases')
      .then((r) => r.json())
      .then(setItems)
      .catch(() => setItems([]))
  }, [])

  const act = useCallback(
    (id: number, action: Action) => {
      setItems((list) => {
        if (!list) return list
        fetch(`/albums/${id}/${action}`, { method: 'POST' }).then(() => onChange?.())
        return list.filter((it) => it.id !== id)
      })
    },
    [onChange],
  )

  if (!items) return <p>Loading…</p>
  if (items.length === 0) return <p>No new releases.</p>

  const shown = items.filter((it) => matchesQuery(`${it.artist} ${it.title}`, query))

  return (
    <table>
      <tbody>
        {shown.map((it) => (
          <tr key={it.id}>
            <Cover id={it.id} hasArt={it.has_art} spotifyId={it.spotify_id} />
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

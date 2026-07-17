import { useCallback, useEffect, useState } from 'react'
import { Cover } from './Cover'
import { matchesQuery } from './filter'

type Item = { id: number; artist: string; title: string; reason: string; has_art: boolean }
type Action = 'keep' | 'drop' | 'snooze'

export function Decide({ onChange, query = '' }: { onChange?: () => void; query?: string }) {
  const [items, setItems] = useState<Item[] | null>(null)
  const [sel, setSel] = useState(0)

  useEffect(() => {
    fetch('/decide')
      .then((r) => r.json())
      .then(setItems)
      .catch(() => setItems([]))
  }, [])

  const act = useCallback(
    (id: number, action: Action) => {
      fetch(`/albums/${id}/${action}`, { method: 'POST' }).then(() => onChange?.())
      setItems((list) => (list ? list.filter((it) => it.id !== id) : list))
    },
    [onChange],
  )

  // Keyboard triage operates on the currently-shown (filtered) rows.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const shown = (items ?? []).filter((it) => matchesQuery(`${it.artist} ${it.title}`, query))
      if (shown.length === 0) return
      const k = e.key.toLowerCase()
      const cur = Math.min(sel, shown.length - 1)
      if (k === 'j' || k === 'arrowdown') setSel(Math.min(cur + 1, shown.length - 1))
      else if (k === 'k' || k === 'arrowup') setSel(Math.max(cur - 1, 0))
      else if (k === 'y') act(shown[cur].id, 'keep')
      else if (k === 'x') act(shown[cur].id, 'drop')
      else if (k === 's') act(shown[cur].id, 'snooze')
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [items, sel, query, act])

  if (!items) return <p>Loading…</p>
  if (items.length === 0) return <p>Nothing to judge.</p>

  const shown = items.filter((it) => matchesQuery(`${it.artist} ${it.title}`, query))
  const cur = Math.min(sel, shown.length - 1)

  return (
    <table>
      <thead>
        <tr>
          <th className="cover-cell" />
          <th>artist</th>
          <th>title</th>
          <th>why</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {shown.map((it, i) => (
          <tr key={it.id} className={i === cur ? 'sel' : undefined}>
            <Cover id={it.id} hasArt={it.has_art} />
            <td>{it.artist}</td>
            <td>{it.title}</td>
            <td className="nowrap">{it.reason}</td>
            <td className="nowrap">
              <button type="button" onClick={() => act(it.id, 'keep')}>
                Keep
              </button>
              <button type="button" onClick={() => act(it.id, 'drop')}>
                Drop
              </button>
              <button type="button" onClick={() => act(it.id, 'snooze')}>
                Snooze
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

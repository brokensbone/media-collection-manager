import { useCallback, useEffect, useState } from 'react'
import { Cover } from './Cover'

type Item = { id: number; artist: string; title: string; reason: string; has_art: boolean }
type Action = 'keep' | 'drop' | 'snooze'

export function Decide() {
  const [items, setItems] = useState<Item[] | null>(null)
  const [sel, setSel] = useState(0)

  useEffect(() => {
    fetch('/decide')
      .then((r) => r.json())
      .then(setItems)
      .catch(() => setItems([]))
  }, [])

  const act = useCallback((index: number, action: Action) => {
    setItems((list) => {
      if (!list?.[index]) return list
      fetch(`/albums/${list[index].id}/${action}`, { method: 'POST' })
      const next = list.filter((_, i) => i !== index)
      setSel((s) => Math.max(0, Math.min(s, next.length - 1)))
      return next
    })
  }, [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!items || items.length === 0) return
      const k = e.key.toLowerCase()
      if (k === 'j' || k === 'arrowdown') setSel((s) => Math.min(s + 1, items.length - 1))
      else if (k === 'k' || k === 'arrowup') setSel((s) => Math.max(s - 1, 0))
      else if (k === 'y') act(sel, 'keep')
      else if (k === 'x') act(sel, 'drop')
      else if (k === 's') act(sel, 'snooze')
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [items, sel, act])

  if (!items) return <p>Loading…</p>
  if (items.length === 0) return <p>Nothing to judge.</p>

  return (
    <table>
      <tbody>
        {items.map((it, i) => (
          <tr key={it.id} className={i === sel ? 'sel' : undefined}>
            <Cover id={it.id} hasArt={it.has_art} />
            <td>{it.artist}</td>
            <td>{it.title}</td>
            <td>{it.reason}</td>
            <td>
              <button type="button" onClick={() => act(i, 'keep')}>
                Keep
              </button>
              <button type="button" onClick={() => act(i, 'drop')}>
                Drop
              </button>
              <button type="button" onClick={() => act(i, 'snooze')}>
                Snooze
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

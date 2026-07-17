import { useCallback, useEffect, useState } from 'react'

type Item = {
  id: number
  source: string
  name: string
  state: 'detected' | 'queued' | 'imported' | 'failed'
  matched_album_id: number | null
  matched: string | null
}

const STATUS: Record<Item['state'], string> = {
  detected: '',
  queued: 'pending…',
  imported: 'imported ✓',
  failed: 'failed',
}

export function Imports({ onChange }: { onChange?: () => void }) {
  const [items, setItems] = useState<Item[] | null>(null)

  const refresh = useCallback(() => {
    fetch('/imports')
      .then((r) => r.json())
      .then(setItems)
      .catch(() => setItems([]))
  }, [])

  // Poll so background imports (queued → imported/failed) update on screen without a reload.
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 4000)
    return () => clearInterval(t)
  }, [refresh])

  const enqueue = useCallback(
    (id: number) => {
      // optimistically show it queued; the poll then tracks it to imported/failed
      setItems(
        (list) => list?.map((it) => (it.id === id ? { ...it, state: 'queued' } : it)) ?? list,
      )
      fetch(`/imports/${id}/import`, { method: 'POST' }).then(() => onChange?.())
    },
    [onChange],
  )

  if (!items) return <p>Loading…</p>
  if (items.length === 0) return <p>No downloads to import.</p>

  return (
    <table>
      <tbody>
        {items.map((it) => (
          <tr key={it.id}>
            <td className="muted">{it.source}</td>
            <td>{it.name}</td>
            <td>{it.matched ?? <span className="muted">no match</span>}</td>
            <td className="nowrap">
              {it.state === 'detected' && (
                <button type="button" onClick={() => enqueue(it.id)}>
                  Import
                </button>
              )}
              {it.state === 'queued' && <span className="muted">{STATUS.queued}</span>}
              {it.state === 'imported' && <span className="muted">{STATUS.imported}</span>}
              {it.state === 'failed' && (
                <>
                  <span className="muted">{STATUS.failed}</span>{' '}
                  <button type="button" onClick={() => enqueue(it.id)}>
                    Retry
                  </button>
                </>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'
import { matchesQuery } from './filter'

type Item = {
  id: number
  source: string
  name: string
  state: 'detected' | 'queued' | 'importing' | 'imported' | 'skipped' | 'failed'
  matched_album_id: number | null
  matched: string | null
  matched_owned: boolean
  missing: boolean
}

const STATUS: Record<Item['state'], string> = {
  detected: '',
  queued: 'queued',
  importing: 'importing…',
  imported: 'imported ✓',
  skipped: 'already in library',
  failed: 'failed',
}

export function Imports({ onChange, query = '' }: { onChange?: () => void; query?: string }) {
  const [items, setItems] = useState<Item[] | null>(null)
  const [scanning, setScanning] = useState(false)

  // Optimistic actions that must outlive a poll: after clicking Import/Discard, an in-flight (or
  // next) /imports poll can still return the pre-action row and flash it back. So we hold the
  // intent here and re-apply it to every poll result until the server catches up — no flicker.
  const pending = useRef<Map<number, 'queued' | 'discarded'>>(new Map())

  const merge = useCallback((data: Item[]): Item[] => {
    const p = pending.current
    const ids = new Set(data.map((it) => it.id))
    for (const it of data) {
      if (p.get(it.id) === 'queued' && it.state !== 'detected') p.delete(it.id) // server caught up
    }
    for (const [id, kind] of [...p]) {
      if (kind === 'discarded' && !ids.has(id)) p.delete(id) // server dismissed it
    }
    return data
      .filter((it) => p.get(it.id) !== 'discarded')
      .map((it) => (p.get(it.id) === 'queued' ? { ...it, state: 'queued' } : it))
  }, [])

  const refresh = useCallback(() => {
    fetch('/imports')
      .then((r) => r.json())
      .then((data: Item[]) => setItems(merge(data)))
      .catch(() => setItems([]))
  }, [merge])

  // Poll so background imports (queued → imported/failed) update on screen without a reload.
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 4000)
    return () => clearInterval(t)
  }, [refresh])

  const enqueue = useCallback(
    (id: number) => {
      // optimistically show it queued (sticky via `pending`); the poll tracks it onward
      pending.current.set(id, 'queued')
      setItems(
        (list) => list?.map((it) => (it.id === id ? { ...it, state: 'queued' } : it)) ?? list,
      )
      fetch(`/imports/${id}/import`, { method: 'POST' }).then(() => {
        onChange?.()
        refresh()
      })
    },
    [onChange, refresh],
  )

  const scan = useCallback(() => {
    setScanning(true)
    fetch('/imports/scan', { method: 'POST' })
      .then(refresh)
      .then(() => onChange?.())
      .finally(() => setScanning(false))
  }, [onChange, refresh])

  const discard = useCallback(
    (id: number) => {
      pending.current.set(id, 'discarded') // sticky removal until the server dismisses it
      setItems((list) => list?.filter((it) => it.id !== id) ?? list)
      fetch(`/imports/${id}`, { method: 'DELETE' }).then(() => {
        onChange?.()
        refresh()
      })
    },
    [onChange, refresh],
  )

  if (!items) return <p>Loading…</p>

  const shown = items.filter((it) => matchesQuery(`${it.name} ${it.matched ?? ''}`, query))

  // Only reflect active work — imported rows persist in the list as history, so counting them
  // would make a single import read as "3 of 3". Imports run one at a time (at most one active).
  const importing = items.some((it) => it.state === 'importing')
  const queued = items.filter((it) => it.state === 'queued').length
  const progress = [importing ? 'Importing…' : null, queued > 0 ? `${queued} queued` : null]
    .filter(Boolean)
    .join(' · ')

  return (
    <>
      <div className="inline-actions">
        <button type="button" onClick={scan} disabled={scanning}>
          {scanning ? 'Scanning…' : 'Scan watch folder'}
        </button>
      </div>
      {items.length === 0 && <p>No downloads to import.</p>}
      {progress && <p className="resolving">{progress}</p>}
      {items.length > 0 && (
        <table>
          <tbody>
            {shown.map((it) => (
              <tr key={it.id}>
                <td className="muted">{it.source}</td>
                <td>{it.name}</td>
                <td>
                  {it.matched ?? <span className="muted">no match</span>}
                  {/* "already owned" is a pre-import warning; pointless once it's imported. */}
                  {it.matched_owned && it.state !== 'imported' && (
                    <span className="badge">owned</span>
                  )}
                </td>
                <td className="nowrap">
                  {it.missing ? (
                    <>
                      <span className="muted">file no longer in watch folder</span>{' '}
                      <button type="button" onClick={() => discard(it.id)}>
                        Discard
                      </button>
                    </>
                  ) : (
                    <>
                      {it.state === 'detected' && (
                        <>
                          <button type="button" onClick={() => enqueue(it.id)}>
                            Import
                          </button>{' '}
                          <button type="button" onClick={() => discard(it.id)}>
                            Discard
                          </button>
                        </>
                      )}
                      {it.state === 'queued' && <span className="muted">{STATUS.queued}</span>}
                      {it.state === 'importing' && (
                        <span className="muted">{STATUS.importing}</span>
                      )}
                      {it.state === 'imported' && <span className="muted">{STATUS.imported}</span>}
                      {it.state === 'skipped' && <span className="muted">{STATUS.skipped}</span>}
                      {it.state === 'failed' && (
                        <>
                          <span className="muted">{STATUS.failed}</span>{' '}
                          <button type="button" onClick={() => enqueue(it.id)}>
                            Retry
                          </button>{' '}
                          <button type="button" onClick={() => discard(it.id)}>
                            Discard
                          </button>
                        </>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'
import { matchesQuery } from './filter'

type Item = {
  id: number
  source: string
  name: string
  media_kind: 'music' | 'tv' | 'film' | 'unknown'
  import_target: 'beets' | 'tv' | 'film' | 'review'
  classification_detail: string | null
  destination_path: string | null
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

// The type a row belongs to for the filter bar. Keyed off import_target so the buckets are
// mutually exclusive and match where the file actually goes: a mixed-season TV pack routed to
// review shows under Review (needs attention), not TV — so each list is a clean batch to work.
type ItemType = 'music' | 'tv' | 'film' | 'review'
const TYPE_LABELS: [ItemType, string][] = [
  ['music', 'Music'],
  ['tv', 'TV'],
  ['film', 'Film'],
  ['review', 'Review'],
]

function itemType(it: Item): ItemType {
  if (it.import_target === 'review') return 'review'
  if (it.import_target === 'tv') return 'tv'
  if (it.import_target === 'film') return 'film'
  return 'music' // beets
}

export function Imports({ onChange, query = '' }: { onChange?: () => void; query?: string }) {
  const [items, setItems] = useState<Item[] | null>(null)
  const [scanning, setScanning] = useState(false)
  const [typeFilter, setTypeFilter] = useState<'all' | ItemType>('all')

  // Optimistic actions that must outlive a poll: after clicking Import/Discard, an in-flight (or
  // next) /imports poll can still return the pre-action row and flash it back. So we hold the
  // intent here and re-apply it to every poll result until the server catches up — no flicker.
  const pending = useRef<Map<number, 'queued' | 'discarded'>>(new Map())

  const merge = useCallback((prev: Item[] | null, data: Item[]): Item[] => {
    const p = pending.current
    const ids = new Set(data.map((it) => it.id))
    for (const it of data) {
      if (p.get(it.id) === 'queued' && it.state !== 'detected') p.delete(it.id) // server caught up
    }
    for (const [id, kind] of [...p]) {
      if (kind === 'discarded' && !ids.has(id)) p.delete(id) // server dismissed it
    }
    const effective: Item[] = data
      .filter((it) => p.get(it.id) !== 'discarded')
      .map((it) => (p.get(it.id) === 'queued' ? { ...it, state: 'queued' as const } : it))
    // Keep rows where they already are: adopting the server's active-first order on every poll
    // makes a row that changes state (e.g. Retry: failed -> queued) jump up the list under the
    // cursor. So preserve the current display order, update rows in place, append only new ones.
    if (!prev) return effective // first load takes the server order
    const byId = new Map(effective.map((it) => [it.id, it]))
    const seen = new Set<number>()
    const kept: Item[] = []
    for (const row of prev) {
      const updated = byId.get(row.id)
      if (updated) {
        kept.push(updated)
        seen.add(row.id)
      }
    }
    return [...kept, ...effective.filter((it) => !seen.has(it.id))]
  }, [])

  const refresh = useCallback(() => {
    fetch('/imports')
      .then((r) => r.json())
      .then((data: Item[]) => setItems((prev) => merge(prev, data)))
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

  const queryFiltered = items.filter((it) => matchesQuery(`${it.name} ${it.matched ?? ''}`, query))
  const counts: Record<ItemType, number> = { music: 0, tv: 0, film: 0, review: 0 }
  for (const it of queryFiltered) counts[itemType(it)]++
  // Only worth a filter bar when more than one type is present; keep the active bucket visible
  // even if it empties out (e.g. you import the last film) so you can always click back to All.
  const present = TYPE_LABELS.filter(([k]) => counts[k] > 0)
  const barTypes = TYPE_LABELS.filter(([k]) => counts[k] > 0 || typeFilter === k)
  const shown =
    typeFilter === 'all' ? queryFiltered : queryFiltered.filter((it) => itemType(it) === typeFilter)

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
      {present.length > 1 && (
        <div className="dashboard">
          <button
            type="button"
            className={typeFilter === 'all' ? 'stat active' : 'stat'}
            onClick={() => setTypeFilter('all')}
          >
            <b>{queryFiltered.length}</b> all
          </button>
          {barTypes.map(([k, label]) => (
            <button
              key={k}
              type="button"
              className={typeFilter === k ? 'stat active' : 'stat'}
              onClick={() => setTypeFilter(k)}
            >
              <b>{counts[k]}</b> {label}
            </button>
          ))}
        </div>
      )}
      {items.length === 0 && <p>No downloads to import.</p>}
      {progress && <p className="resolving">{progress}</p>}
      {items.length > 0 && shown.length === 0 && (
        <p className="muted">Nothing to show for this filter.</p>
      )}
      {shown.length > 0 && (
        <table>
          <tbody>
            {shown.map((it) => (
              <tr key={it.id}>
                <td className="muted">{it.source}</td>
                <td>
                  <div>{it.name}</div>
                  <div className="muted">
                    {labelKind(it.media_kind)}
                    {it.classification_detail ? ` · ${it.classification_detail}` : ''}
                  </div>
                  {it.destination_path && <div className="muted">{it.destination_path}</div>}
                </td>
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
                      {it.state === 'detected' && it.import_target !== 'review' && (
                        <>
                          <button type="button" onClick={() => enqueue(it.id)}>
                            Import
                          </button>{' '}
                          <button type="button" onClick={() => discard(it.id)}>
                            Discard
                          </button>
                        </>
                      )}
                      {it.state === 'detected' && it.import_target === 'review' && (
                        <>
                          <span className="muted">needs review</span>{' '}
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

function labelKind(kind: Item['media_kind']): string {
  if (kind === 'tv') return 'TV'
  if (kind === 'film') return 'Film'
  if (kind === 'music') return 'Music'
  return 'Unknown'
}

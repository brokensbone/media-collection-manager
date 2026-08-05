import { useCallback, useEffect, useRef, useState } from 'react'
import { matchesQuery } from './filter'
import { type ImportItem, dayLabel, labelKind } from './importItem'
import { ImportReclassify } from './importReclassify'

// The type a row belongs to for the filter bar. Keyed off import_target so the buckets are
// mutually exclusive and match where the file actually goes: a mixed-season TV pack routed to
// review shows under Review (needs attention), not TV — so each list is a clean batch to work.
type ItemType = 'music' | 'tv' | 'film' | 'workspace' | 'review'
const TYPE_LABELS: [ItemType, string][] = [
  ['music', 'Music'],
  ['tv', 'TV'],
  ['film', 'Film'],
  ['workspace', 'Workspace'],
  ['review', 'Review'],
]

function itemType(it: ImportItem): ItemType {
  if (it.import_target === 'review') return 'review'
  if (it.import_target === 'workspace') return 'workspace'
  if (it.import_target === 'tv') return 'tv'
  if (it.import_target === 'film') return 'film'
  return 'music' // beets
}

export function Imports({ onChange, query = '' }: { onChange?: () => void; query?: string }) {
  const [items, setItems] = useState<ImportItem[] | null>(null)
  const [scanning, setScanning] = useState(false)
  const [typeFilter, setTypeFilter] = useState<'all' | ItemType>('all')

  // Import/Discard both remove the row from this decision list (it becomes a Task, or is
  // dismissed). Hold the removed ids so an in-flight poll can't flash a row back before the
  // server catches up; drop the id once the server stops returning it.
  const removed = useRef<Set<number>>(new Set())

  const merge = useCallback((prev: ImportItem[] | null, data: ImportItem[]): ImportItem[] => {
    const ids = new Set(data.map((it) => it.id))
    for (const id of [...removed.current]) if (!ids.has(id)) removed.current.delete(id)
    const effective = data.filter((it) => !removed.current.has(it.id))
    if (!prev) return effective
    // Preserve display order so a poll never reshuffles rows under the cursor; append new ones.
    const byId = new Map(effective.map((it) => [it.id, it]))
    const seen = new Set<number>()
    const kept: ImportItem[] = []
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
      .then((data: ImportItem[]) => setItems((prev) => merge(prev, data)))
      .catch(() => setItems([]))
  }, [merge])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 4000)
    return () => clearInterval(t)
  }, [refresh])

  const act = useCallback(
    (id: number, method: 'POST' | 'DELETE') => {
      removed.current.add(id) // sticky removal until the server stops listing it as pending
      setItems((list) => list?.filter((it) => it.id !== id) ?? list)
      const url = method === 'POST' ? `/imports/${id}/import` : `/imports/${id}`
      fetch(url, { method }).then(() => {
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

  if (!items) return <p>Loading…</p>

  const queryFiltered = items.filter((it) => matchesQuery(`${it.name} ${it.matched ?? ''}`, query))
  const counts: Record<ItemType, number> = {
    music: 0,
    tv: 0,
    film: 0,
    workspace: 0,
    review: 0,
  }
  for (const it of queryFiltered) counts[itemType(it)]++
  const present = TYPE_LABELS.filter(([k]) => counts[k] > 0)
  const barTypes = TYPE_LABELS.filter(([k]) => counts[k] > 0 || typeFilter === k)
  const shown =
    typeFilter === 'all' ? queryFiltered : queryFiltered.filter((it) => itemType(it) === typeFilter)

  // Partition into discovery-day groups, newest first, so freshly-added drops are easy to find
  // instead of scattering alphabetically. created_at is immutable, so this order never reshuffles.
  const sorted = [...shown].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))
  const groups: { key: string; label: string; rows: ImportItem[] }[] = []
  for (const it of sorted) {
    const key = it.created_at ? new Date(it.created_at).toDateString() : 'unknown'
    const g = groups.find((x) => x.key === key)
    if (g) g.rows.push(it)
    else groups.push({ key, label: dayLabel(it.created_at), rows: [it] })
  }

  const table = (rows: ImportItem[]) => (
    <table>
      <colgroup>
        <col className="c-source" />
        <col />
        <col className="c-matched" />
        <col className="c-actions3" />
      </colgroup>
      <tbody>
        {rows.map((it) => (
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
              {it.matched_owned && <span className="badge">owned</span>}
            </td>
            <td className="nowrap">
              <ImportReclassify item={it} onChange={refresh} disabled={it.missing} />{' '}
              {it.missing ? (
                <>
                  <span className="muted">file no longer in watch folder</span>{' '}
                  <button type="button" onClick={() => act(it.id, 'DELETE')}>
                    Discard
                  </button>
                </>
              ) : it.import_target === 'review' ? (
                <>
                  <span className="muted">needs review</span>{' '}
                  <button type="button" onClick={() => act(it.id, 'DELETE')}>
                    Discard
                  </button>
                </>
              ) : (
                <>
                  <button type="button" onClick={() => act(it.id, 'POST')}>
                    Import
                  </button>{' '}
                  <button type="button" onClick={() => act(it.id, 'DELETE')}>
                    Discard
                  </button>
                </>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )

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
      {items.length === 0 && <p>Nothing waiting to import.</p>}
      {items.length > 0 && shown.length === 0 && (
        <p className="muted">Nothing to show for this filter.</p>
      )}
      {groups.map((g) => (
        <section key={g.key}>
          <h3 className="task-group">
            {g.label} <span className="muted">({g.rows.length})</span>
          </h3>
          {table(g.rows)}
        </section>
      ))}
    </>
  )
}

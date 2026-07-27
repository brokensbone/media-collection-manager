import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { type ImportItem, type ImportState, labelKind, whenLabel } from './importItem'

const STATUS: Record<ImportState, string> = {
  detected: '',
  queued: 'queued',
  importing: 'importing…',
  imported: 'imported ✓',
  skipped: 'already in library',
  failed: 'failed',
}

// Status groups shown top-to-bottom in the Tasks view. Completed (imported/skipped) is last and,
// in the default view, limited to the recent window server-side; the archive shows all of it.
const GROUPS: { label: string; states: ImportState[] }[] = [
  { label: 'In progress', states: ['importing'] },
  { label: 'Queued', states: ['queued'] },
  { label: 'Failed', states: ['failed'] },
  { label: 'Completed', states: ['imported', 'skipped'] },
]

export function Tasks({
  onChange,
  query = '',
  archive = false,
}: {
  onChange?: () => void
  query?: string
  archive?: boolean
}) {
  const [items, setItems] = useState<ImportItem[] | null>(null)
  const [openLog, setOpenLog] = useState<number | null>(null)
  const removed = useRef<Set<number>>(new Set())

  const refresh = useCallback(() => {
    fetch(archive ? '/imports/archive' : '/imports/tasks')
      .then((r) => r.json())
      .then((data: ImportItem[]) => setItems(data.filter((it) => !removed.current.has(it.id))))
      .catch(() => setItems([]))
  }, [archive])

  // Poll the live Tasks view so queued → importing → completed updates on screen; the archive is
  // historical, so fetch it once.
  useEffect(() => {
    refresh()
    if (archive) return
    const t = setInterval(refresh, 4000)
    return () => clearInterval(t)
  }, [refresh, archive])

  const act = useCallback(
    (id: number, method: 'POST' | 'DELETE') => {
      if (method === 'DELETE') {
        removed.current.add(id)
        setItems((list) => list?.filter((it) => it.id !== id) ?? list)
      }
      const url = method === 'POST' ? `/imports/${id}/import` : `/imports/${id}`
      fetch(url, { method }).then(() => {
        onChange?.()
        refresh()
      })
    },
    [onChange, refresh],
  )

  if (!items) return <p>Loading…</p>

  const shown = query
    ? items.filter((it) =>
        `${it.name} ${it.matched ?? ''}`.toLowerCase().includes(query.toLowerCase()),
      )
    : items

  const rows = (list: ImportItem[]) => (
    <table>
      <colgroup>
        <col className="c-source" />
        <col />
        <col className="c-aux" />
        <col className="c-actions3" />
      </colgroup>
      <tbody>
        {list.map((it) => (
          <Fragment key={it.id}>
            <tr>
              <td className="muted">{it.source}</td>
              <td>
                <div>{it.name}</div>
                <div className="muted">
                  {labelKind(it.media_kind)}
                  {it.matched ? ` · ${it.matched}` : ''}
                </div>
                {it.destination_path && <div className="muted">{it.destination_path}</div>}
              </td>
              <td className="muted nowrap">{whenLabel(it.updated_at)}</td>
              <td className="nowrap">
                <span className="muted">{STATUS[it.state]}</span>
                {it.state === 'failed' && (
                  <>
                    {' '}
                    {it.error_detail && (
                      <button
                        type="button"
                        onClick={() => setOpenLog((cur) => (cur === it.id ? null : it.id))}
                      >
                        {openLog === it.id ? 'Hide log' : 'Log'}
                      </button>
                    )}{' '}
                    <button type="button" onClick={() => act(it.id, 'POST')}>
                      Retry
                    </button>{' '}
                    <button type="button" onClick={() => act(it.id, 'DELETE')}>
                      Discard
                    </button>
                  </>
                )}
              </td>
            </tr>
            {openLog === it.id && it.error_detail && (
              <tr>
                <td colSpan={4}>
                  <pre className="import-log">{it.error_detail}</pre>
                </td>
              </tr>
            )}
          </Fragment>
        ))}
      </tbody>
    </table>
  )

  if (archive) {
    return (
      <>
        <div className="inline-actions">
          <button type="button" className="linklike" onClick={() => setHash('tasks')}>
            ← Back to tasks
          </button>
        </div>
        {shown.length === 0 ? <p className="muted">No completed imports.</p> : rows(shown)}
      </>
    )
  }

  const groups = GROUPS.map((g) => ({
    ...g,
    rows: shown.filter((it) => g.states.includes(it.state)),
  })).filter((g) => g.rows.length > 0)

  return (
    <>
      {groups.length === 0 && <p>No import tasks.</p>}
      {groups.map((g) => (
        <section key={g.label}>
          <h3 className="task-group">
            {g.label} <span className="muted">({g.rows.length})</span>
          </h3>
          {rows(g.rows)}
        </section>
      ))}
      <div className="inline-actions">
        <button type="button" className="linklike" onClick={() => setHash('archive')}>
          View completed archive →
        </button>
      </div>
    </>
  )
}

function setHash(h: string): void {
  window.location.hash = h
}

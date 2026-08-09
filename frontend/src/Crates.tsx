import { useCallback, useEffect, useMemo, useState } from 'react'

// A crate view: the box the operator is looking at, its ancestors, its sub-boxes, and the
// records loose directly here. Mirrors the backend's BoxView (crates §2).
type Crumb = { id: number; name: string }
type ChildBox = { id: number; name: string; loose_count: number; total_count: number }
type BoxRecord = {
  beets_id: string
  artist: string
  title: string
  year: number | null
  media: string | null
}
type BoxView = {
  id: number
  name: string
  parent_id: number | null
  breadcrumb: Crumb[]
  children: ChildBox[]
  records: BoxRecord[]
  loose_count: number
  total_count: number
  soft_cap: number
  over_cap: boolean
}

// A proposed way to divide this box's loose records into sub-boxes (crates §4). Mirrors the
// backend's SplitCandidate: one axis, the groups it would create, and how many records it leaves
// loose.
type SplitGroup = { name: string; count: number }
type SplitCandidate = {
  key: string
  label: string
  groups: SplitGroup[]
  covers: number
  leaves: number
}

// The box being viewed lives in the URL (#crates?box=<id>) so descending, breadcrumbs and the
// browser back button all work. No box param = the root Collection.
function boxIdFromHash(): number | null {
  const query = window.location.hash.split('?')[1] ?? ''
  const raw = new URLSearchParams(query).get('box')
  return raw ? Number(raw) : null
}

function gotoBox(id: number | null) {
  window.location.hash = id == null ? 'crates' : `crates?box=${id}`
}

export function Crates() {
  const [boxId, setBoxId] = useState<number | null>(() => boxIdFromHash())
  const [view, setView] = useState<BoxView | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [newSub, setNewSub] = useState('')
  const [newTarget, setNewTarget] = useState('')
  // null = the split panel is closed; an array (possibly empty) = suggestions have been fetched.
  const [splits, setSplits] = useState<SplitCandidate[] | null>(null)

  useEffect(() => {
    const onHash = () => setBoxId(boxIdFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const load = useCallback(() => {
    const url = boxId == null ? '/crates/box' : `/crates/box/${boxId}`
    fetch(url)
      .then((r) => r.json())
      .then((v: BoxView) => {
        setView(v)
        setSelected(new Set())
        setSplits(null) // stale after any reload — the loose set it was computed from has changed
      })
      .catch(() => setView(null))
  }, [boxId])

  useEffect(load, [load])

  // Post a mutation, surface any rejection (e.g. a blocked delete), then reload the view.
  const act = useCallback(async (url: string, init: RequestInit): Promise<boolean> => {
    setError(null)
    const r = await fetch(url, {
      ...init,
      headers: { 'content-type': 'application/json', ...(init.headers ?? {}) },
    })
    if (!r.ok) {
      const body = await r.json().catch(() => null)
      setError(body?.detail ?? 'That didn’t work.')
      return false
    }
    return true
  }, [])

  const ids = useMemo(() => Array.from(selected), [selected])

  if (!view) return <p>Loading…</p>

  const toggle = (beetsId: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(beetsId)) next.delete(beetsId)
      else next.add(beetsId)
      return next
    })
  }

  const createSub = async () => {
    if (!newSub.trim()) return
    if (
      await act('/crates/box', {
        method: 'POST',
        body: JSON.stringify({ name: newSub.trim(), parent_id: view.id }),
      })
    ) {
      setNewSub('')
      load()
    }
  }

  const rename = async () => {
    const name = window.prompt('Rename box', view.name)?.trim()
    if (
      name &&
      (await act(`/crates/box/${view.id}`, { method: 'PATCH', body: JSON.stringify({ name }) }))
    )
      load()
  }

  const remove = async () => {
    if (await act(`/crates/box/${view.id}`, { method: 'DELETE' })) gotoBox(view.parent_id)
  }

  const kickUp = async () => {
    if (
      await act(`/crates/box/${view.id}/kick-up`, {
        method: 'POST',
        body: JSON.stringify({ beets_ids: ids }),
      })
    )
      load()
  }

  const fileInto = async (childId: number) => {
    if (
      await act(`/crates/box/${view.id}/file`, {
        method: 'POST',
        body: JSON.stringify({ beets_ids: ids, child_box_id: childId }),
      })
    )
      load()
  }

  const fileNew = async () => {
    if (!newTarget.trim()) return
    if (
      await act(`/crates/box/${view.id}/file`, {
        method: 'POST',
        body: JSON.stringify({ beets_ids: ids, new_box_name: newTarget.trim() }),
      })
    ) {
      setNewTarget('')
      load()
    }
  }

  const suggestSplit = async () => {
    setError(null)
    const r = await fetch(`/crates/box/${view.id}/split-suggestions`)
    setSplits(r.ok ? await r.json() : [])
  }

  const applySplit = async (facet: string) => {
    if (
      await act(`/crates/box/${view.id}/split`, {
        method: 'POST',
        body: JSON.stringify({ facet }),
      })
    )
      load() // reload shows the new sub-boxes and clears the (now stale) suggestions panel
  }

  const isRoot = view.parent_id == null
  const capPct = Math.min(100, Math.round((view.loose_count / Math.max(1, view.soft_cap)) * 100))

  return (
    <section className="crates">
      <nav className="crumbs" aria-label="Breadcrumb">
        {view.breadcrumb.map((c, i) => (
          <span key={c.id}>
            {i > 0 && <span className="crumb-sep"> › </span>}
            {c.id === view.id ? (
              <span className="crumb-here">{c.name}</span>
            ) : (
              <button type="button" className="linklike" onClick={() => gotoBox(c.id)}>
                {c.name}
              </button>
            )}
          </span>
        ))}
      </nav>

      <div className="crate-head">
        <h2>{view.name}</h2>
        {!isRoot && (
          <div className="crate-tools">
            <button type="button" className="linklike" onClick={rename}>
              Rename
            </button>
            <button type="button" className="linklike" onClick={remove}>
              Delete
            </button>
          </div>
        )}
      </div>

      <div className={`cap-meter${view.over_cap ? ' over' : ''}`}>
        <div className="cap-bar">
          <div className="cap-fill" style={{ width: `${capPct}%` }} />
        </div>
        <span className="cap-label">
          {view.loose_count} loose / {view.soft_cap}
          {view.over_cap && ' — getting full, consider splitting into sub-boxes'}
        </span>
      </div>

      {error && <p className="crate-error">{error}</p>}

      <div className="tiles">
        {view.children.map((c) => (
          <button type="button" key={c.id} className="tile" onClick={() => gotoBox(c.id)}>
            <span className="tile-name">{c.name}</span>
            <span className="tile-count">{c.total_count}</span>
          </button>
        ))}
        <div className="tile tile-new">
          <input
            type="text"
            placeholder="new sub-box…"
            value={newSub}
            onChange={(e) => setNewSub(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && createSub()}
          />
          <button type="button" onClick={createSub}>
            Add
          </button>
        </div>
        <button type="button" className="tile suggest-split" onClick={suggestSplit}>
          ✨ Suggest a split
        </button>
      </div>

      {splits !== null &&
        (splits.length === 0 ? (
          <p className="muted">No clean split found — file by hand.</p>
        ) : (
          <div className="splits">
            {splits.map((s) => (
              <div key={s.key} className="split">
                <span className="split-desc">
                  <strong>{s.label}</strong> —{' '}
                  {s.groups.map((g) => `${g.name} (${g.count})`).join(' · ')} — leaves {s.leaves}{' '}
                  loose
                </span>
                <button type="button" onClick={() => applySplit(s.key)}>
                  Apply
                </button>
              </div>
            ))}
          </div>
        ))}

      {ids.length > 0 && (
        <div className="move-bar">
          <span className="muted">{ids.length} selected</span>
          <button type="button" onClick={kickUp} disabled={isRoot}>
            Kick up
          </button>
          {view.children.length > 0 && (
            <label>
              Move to{' '}
              <select value="" onChange={(e) => e.target.value && fileInto(Number(e.target.value))}>
                <option value="">a sub-box…</option>
                {view.children.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <span className="move-new">
            <input
              type="text"
              placeholder="or a new box…"
              value={newTarget}
              onChange={(e) => setNewTarget(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && fileNew()}
            />
            <button type="button" onClick={fileNew}>
              Move
            </button>
          </span>
        </div>
      )}

      {view.records.length === 0 ? (
        <p className="muted">Nothing loose here.</p>
      ) : (
        <table className="loose">
          <tbody>
            {view.records.map((r) => (
              <tr key={r.beets_id} className={selected.has(r.beets_id) ? 'sel' : undefined}>
                <td className="c-check">
                  <input
                    type="checkbox"
                    aria-label={`Select ${r.artist} — ${r.title}`}
                    checked={selected.has(r.beets_id)}
                    onChange={() => toggle(r.beets_id)}
                  />
                </td>
                <td>{r.artist}</td>
                <td>{r.title}</td>
                <td className="muted">{[r.year, r.media].filter(Boolean).join(' · ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

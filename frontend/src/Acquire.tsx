import { useCallback, useEffect, useState } from 'react'
import { Cover } from './Cover'
import { Modal } from './Modal'
import { matchesQuery } from './filter'

type Item = {
  id: number
  artist: string
  title: string
  has_art: boolean
  bandcamp_url: string
  possibly_owned: boolean
  owned_hint: string | null
  spotify_id: string | null
}

type Candidate = {
  beets_id: string
  artist: string
  title: string
  has_release_group: boolean
}

export function Acquire({ onChange, query = '' }: { onChange?: () => void; query?: string }) {
  const [items, setItems] = useState<Item[] | null>(null)
  const [owning, setOwning] = useState<Item | null>(null) // the album being marked owned
  const [q, setQ] = useState('')
  const [results, setResults] = useState<Candidate[] | null>(null)

  useEffect(() => {
    fetch('/acquire')
      .then((r) => r.json())
      .then(setItems)
      .catch(() => setItems([]))
  }, [])

  // Search the library while the Mark-owned modal is open.
  useEffect(() => {
    if (!owning) return
    let cancelled = false
    fetch(`/library/search?q=${encodeURIComponent(q)}`)
      .then((r) => r.json())
      .then((r) => !cancelled && setResults(r))
      .catch(() => !cancelled && setResults([]))
    return () => {
      cancelled = true
    }
  }, [owning, q])

  const remove = useCallback((id: number) => {
    setItems((list) => (list ? list.filter((it) => it.id !== id) : list))
  }, [])

  const openOwn = useCallback((it: Item) => {
    setOwning(it)
    setQ(`${it.artist} ${it.title}`)
    setResults(null)
  }, [])

  const markOwned = useCallback(
    (id: number, beetsId?: string) => {
      fetch(`/albums/${id}/mark-owned`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ beets_id: beetsId ?? null }),
      }).then(() => onChange?.())
      remove(id)
      setOwning(null)
    },
    [remove, onChange],
  )

  if (!items) return <p>Loading…</p>
  if (items.length === 0) return <p>Nothing to acquire.</p>

  const shown = items.filter((it) => matchesQuery(`${it.artist} ${it.title}`, query))

  return (
    <>
      <table>
        <colgroup>
          <col className="c-cover" />
          <col className="c-artist" />
          <col />
          <col className="c-link" />
          <col className="c-actions1" />
        </colgroup>
        <tbody>
          {shown.map((it) => (
            <tr key={it.id}>
              <Cover id={it.id} hasArt={it.has_art} spotifyId={it.spotify_id} />
              <td>{it.artist}</td>
              <td>
                {it.title}
                {it.possibly_owned && <div className="muted">possibly owned: {it.owned_hint}</div>}
              </td>
              <td>
                <a href={it.bandcamp_url} target="_blank" rel="noreferrer">
                  Bandcamp
                </a>
              </td>
              <td className="nowrap">
                <button type="button" onClick={() => openOwn(it)}>
                  Mark owned…
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {owning && (
        <Modal
          title={`Mark owned: ${owning.artist} — ${owning.title}`}
          onClose={() => setOwning(null)}
        >
          <input
            type="search"
            className="filter"
            ref={(el) => el?.focus()}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="search your library…"
          />
          <div className="candidates">
            {results === null ? (
              <span className="muted">Searching…</span>
            ) : results.length === 0 ? (
              <span className="muted">No library matches — try a different search.</span>
            ) : (
              results.map((c) => (
                <button
                  key={c.beets_id}
                  type="button"
                  onClick={() => markOwned(owning.id, c.beets_id)}
                >
                  {c.artist} — {c.title}
                  {!c.has_release_group && <span className="muted"> · no MB id</span>}
                </button>
              ))
            )}
          </div>
          <div className="modal-actions">
            <button type="button" onClick={() => markOwned(owning.id)}>
              Mark owned without a link
            </button>
          </div>
        </Modal>
      )}
    </>
  )
}

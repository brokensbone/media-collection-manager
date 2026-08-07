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
  album_type: string | null
}

type Candidate = {
  beets_id: string
  artist: string
  title: string
  has_release_group: boolean
}

// A tracker torrent-search URL for the album. Artist and title go in tab-separated — the
// trackers' own copy links put a tab between them — which URLSearchParams encodes as %09
// (spaces as +). `extra` carries any fixed query params a tracker's basic search needs.
function trackerSearch(
  base: string,
  artist: string,
  title: string,
  extra: Record<string, string> = {},
): string {
  return `${base}?${new URLSearchParams({ searchstr: `${artist}\t${title}`, ...extra })}`
}

// Orpheus's basic search needs these fixed params alongside searchstr.
const ORPHEUS_PARAMS = {
  tags_type: '1',
  order: 'time',
  sort: 'desc',
  group_results: '1',
  action: 'basic',
  searchsubmit: '1',
}

export function Acquire({
  onChange,
  query = '',
}: {
  onChange?: () => void
  query?: string
}) {
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

  const returnToSaved = useCallback(
    (id: number) => {
      fetch(`/albums/${id}/return-to-saved`, { method: 'POST' }).then(() => onChange?.())
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
          <col className="c-artist acquire-artist-col" />
          <col />
          <col className="c-link acquire-link-col" />
          <col className="c-actions1 acquire-actions-col" />
        </colgroup>
        <tbody>
          {shown.map((it) => (
            <tr key={it.id}>
              <Cover id={it.id} hasArt={it.has_art} spotifyId={it.spotify_id} />
              <td>{it.artist}</td>
              <td>
                {it.title}
                {it.album_type && <span className="badge">{it.album_type}</span>}
                {it.possibly_owned && <div className="muted">possibly owned: {it.owned_hint}</div>}
              </td>
              <td>
                <div className="acquire-links">
                  <a href={it.bandcamp_url} target="_blank" rel="noreferrer">
                    Bandcamp
                  </a>
                  <div className="acquire-trackers">
                    <a
                      href={trackerSearch('https://redacted.sh/torrents.php', it.artist, it.title)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Red
                    </a>
                    <a
                      href={trackerSearch(
                        'https://orpheus.network/torrents.php',
                        it.artist,
                        it.title,
                        ORPHEUS_PARAMS,
                      )}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Ops
                    </a>
                  </div>
                </div>
              </td>
              <td>
                <div className="acquire-actions">
                  <button type="button" onClick={() => returnToSaved(it.id)}>
                    Back to saved
                  </button>
                  <button type="button" onClick={() => openOwn(it)}>
                    Mark owned…
                  </button>
                </div>
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
                  {!c.has_release_group && <span className="muted"> {'· no MB id'}</span>}
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

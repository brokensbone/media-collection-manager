import { useCallback, useEffect, useState } from 'react'
import { Cover } from './Cover'

type Item = {
  id: number
  artist: string
  title: string
  has_art: boolean
  bandcamp_url: string
  possibly_owned: boolean
  owned_hint: string | null
}

type Candidate = {
  beets_id: string
  artist: string
  title: string
  has_release_group: boolean
  score: number
}

export function Acquire({ onChange }: { onChange?: () => void }) {
  const [items, setItems] = useState<Item[] | null>(null)
  const [linking, setLinking] = useState<number | null>(null)
  const [candidates, setCandidates] = useState<Candidate[] | null>(null)

  useEffect(() => {
    fetch('/acquire')
      .then((r) => r.json())
      .then(setItems)
      .catch(() => setItems([]))
  }, [])

  const remove = useCallback((id: number) => {
    setItems((list) => (list ? list.filter((it) => it.id !== id) : list))
  }, [])

  const order = useCallback(
    (id: number) => {
      fetch(`/albums/${id}/order`, { method: 'POST' }).then(() => onChange?.())
      remove(id)
    },
    [remove, onChange],
  )

  const markOwned = useCallback(
    (id: number, beetsId?: string) => {
      fetch(`/albums/${id}/mark-owned`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ beets_id: beetsId ?? null }),
      }).then(() => onChange?.())
      setLinking(null)
      setCandidates(null)
      remove(id)
    },
    [remove, onChange],
  )

  const startLinking = useCallback((id: number) => {
    setLinking(id)
    setCandidates(null)
    fetch(`/albums/${id}/link-candidates`)
      .then((r) => r.json())
      .then(setCandidates)
      .catch(() => setCandidates([]))
  }, [])

  if (!items) return <p>Loading…</p>
  if (items.length === 0) return <p>Nothing to acquire.</p>

  return (
    <table>
      <tbody>
        {items.map((it) => (
          <tr key={it.id}>
            <Cover id={it.id} hasArt={it.has_art} />
            <td>{it.artist}</td>
            <td>
              {it.title}
              {it.possibly_owned && <div className="muted">possibly owned: {it.owned_hint}</div>}
            </td>
            <td>
              <a href={it.bandcamp_url} target="_blank" rel="noreferrer">
                Buy on Bandcamp
              </a>
            </td>
            <td className="nowrap">
              <button type="button" onClick={() => order(it.id)}>
                Mark ordered
              </button>
              <button type="button" onClick={() => startLinking(it.id)}>
                Mark owned…
              </button>
              {linking === it.id && (
                <div className="candidates">
                  {candidates === null ? (
                    <span className="muted">Searching library…</span>
                  ) : (
                    <>
                      {candidates.map((c) => (
                        <button
                          key={c.beets_id}
                          type="button"
                          onClick={() => markOwned(it.id, c.beets_id)}
                        >
                          Link: {c.artist} — {c.title}
                        </button>
                      ))}
                      <button type="button" onClick={() => markOwned(it.id)}>
                        Mark owned (no link)
                      </button>
                    </>
                  )}
                </div>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

import { useEffect, useState } from 'react'
import { Cover } from './Cover'
import { matchesQuery } from './filter'

// Owned is the beets library itself — everything you actually own — with Spotify overlaid where
// a release-group matches (cover art + an "on Spotify" marker). Unmatched albums still show.
type OwnedAlbum = {
  beets_id: string
  artist: string
  title: string
  album_id: number | null
  has_art: boolean
  on_spotify: boolean
  spotify_id: string | null
}

export function Owned({ refreshKey = 0, query = '' }: { refreshKey?: number; query?: string }) {
  const [albums, setAlbums] = useState<OwnedAlbum[] | null>(null)
  // The linked/highlighted album is carried in the URL (#owned?sel=<beets_id>) so a specific
  // library entry can be shared by link — e.g. to point at one of a pair of duplicates.
  const [sel, setSel] = useState<string | null>(() => selFromHash())

  // biome-ignore lint/correctness/useExhaustiveDependencies: refreshKey is a manual refetch trigger
  useEffect(() => {
    fetch('/owned')
      .then((r) => r.json())
      .then(setAlbums)
      .catch(() => setAlbums([]))
  }, [refreshKey])

  // Follow the URL so a shared #owned?sel=… link (or back/forward) highlights that row.
  useEffect(() => {
    const onHash = () => setSel(selFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // Bring a linked album into view once its row has rendered.
  useEffect(() => {
    if (!sel || !albums) return
    document.getElementById(`owned-${sel}`)?.scrollIntoView?.({ block: 'center' })
  }, [sel, albums])

  if (!albums) return <p>Loading…</p>
  if (albums.length === 0) return <p>Nothing here.</p>

  const shown = albums.filter((a) => matchesQuery(`${a.artist} ${a.title}`, query))

  return (
    <table>
      <colgroup>
        <col className="c-cover" />
        <col className="c-artist" />
        <col />
        <col className="c-aux" />
      </colgroup>
      <tbody>
        {shown.map((a) => (
          <tr
            key={a.beets_id}
            id={`owned-${a.beets_id}`}
            className={sel === a.beets_id ? 'linked' : undefined}
          >
            <Cover id={a.album_id ?? 0} hasArt={a.has_art} spotifyId={a.spotify_id} />
            <td>{a.artist}</td>
            <td>{a.title}</td>
            <td className="muted nowrap">
              {a.on_spotify ? 'on Spotify ' : ''}
              <a
                className="row-link"
                href={`#owned?sel=${encodeURIComponent(a.beets_id)}`}
                title="Link to this album"
              >
                #
              </a>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// The `sel` param from a #owned?sel=… URL, or null.
function selFromHash(): string | null {
  const query = window.location.hash.split('?')[1] ?? ''
  return new URLSearchParams(query).get('sel')
}

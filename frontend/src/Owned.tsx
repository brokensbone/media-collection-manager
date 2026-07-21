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
}

export function Owned({ refreshKey = 0, query = '' }: { refreshKey?: number; query?: string }) {
  const [albums, setAlbums] = useState<OwnedAlbum[] | null>(null)

  // biome-ignore lint/correctness/useExhaustiveDependencies: refreshKey is a manual refetch trigger
  useEffect(() => {
    fetch('/owned')
      .then((r) => r.json())
      .then(setAlbums)
      .catch(() => setAlbums([]))
  }, [refreshKey])

  if (!albums) return <p>Loading…</p>
  if (albums.length === 0) return <p>Nothing here.</p>

  const shown = albums.filter((a) => matchesQuery(`${a.artist} ${a.title}`, query))

  return (
    <table>
      <tbody>
        {shown.map((a) => (
          <tr key={a.beets_id}>
            <Cover id={a.album_id ?? 0} hasArt={a.has_art} />
            <td>{a.artist}</td>
            <td>{a.title}</td>
            <td className="muted">{a.on_spotify ? 'on Spotify' : ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

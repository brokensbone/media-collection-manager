import { useEffect, useState } from 'react'
import { Cover } from './Cover'
import { matchesQuery } from './filter'

type Album = {
  id: number
  artist: string
  title: string
  state: string
  owned: boolean
  has_art: boolean
}

export function Library({
  state,
  refreshKey = 0,
  query = '',
}: { state?: string; refreshKey?: number; query?: string }) {
  const [albums, setAlbums] = useState<Album[] | null>(null)

  // biome-ignore lint/correctness/useExhaustiveDependencies: refreshKey is a manual refetch trigger
  useEffect(() => {
    const url = state ? `/albums?state=${state}` : '/albums'
    fetch(url)
      .then((r) => r.json())
      .then(setAlbums)
      .catch(() => setAlbums([]))
  }, [state, refreshKey])

  if (!albums) return <p>Loading…</p>
  if (albums.length === 0) return <p>Nothing here.</p>

  const shown = albums.filter((a) => matchesQuery(`${a.artist} ${a.title}`, query))

  return (
    <table>
      <tbody>
        {shown.map((a) => (
          <tr key={a.id}>
            <Cover id={a.id} hasArt={a.has_art} />
            <td>{a.artist}</td>
            <td>{a.title}</td>
            <td>{a.owned ? 'owned' : a.state}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

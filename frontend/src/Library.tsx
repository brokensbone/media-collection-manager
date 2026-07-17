import { useEffect, useState } from 'react'
import { Cover } from './Cover'

type Album = {
  id: number
  artist: string
  title: string
  state: string
  owned: boolean
  has_art: boolean
}

export function Library({ state }: { state?: string }) {
  const [albums, setAlbums] = useState<Album[] | null>(null)

  useEffect(() => {
    const url = state ? `/albums?state=${state}` : '/albums'
    fetch(url)
      .then((r) => r.json())
      .then(setAlbums)
      .catch(() => setAlbums([]))
  }, [state])

  if (!albums) return <p>Loading…</p>
  if (albums.length === 0) return <p>Nothing here.</p>

  return (
    <table>
      <tbody>
        {albums.map((a) => (
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

import { useEffect, useState } from 'react'

type Album = {
  id: number
  artist: string
  title: string
  state: string
  owned: boolean
}

export function Library() {
  const [albums, setAlbums] = useState<Album[] | null>(null)

  useEffect(() => {
    fetch('/albums')
      .then((r) => r.json())
      .then(setAlbums)
      .catch(() => setAlbums([]))
  }, [])

  if (!albums) return <p>Loading…</p>
  if (albums.length === 0) return <p>No albums yet.</p>

  return (
    <table>
      <tbody>
        {albums.map((a) => (
          <tr key={a.id}>
            <td>{a.artist}</td>
            <td>{a.title}</td>
            <td>{a.owned ? 'owned' : a.state}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

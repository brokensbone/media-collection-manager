// Small album-art thumbnail cell (§8e). Art is served from the API at /art/<id>; `hasArt`
// tells us whether a blob exists so we show a quiet placeholder rather than a broken image.
// With `spotifyId`, the cover links to the album on Spotify, opening in a new tab.
export function Cover({
  id,
  hasArt,
  spotifyId,
}: { id: number; hasArt: boolean; spotifyId?: string | null }) {
  const img = hasArt ? (
    <img className="cover" src={`/art/${id}`} alt="" loading="lazy" />
  ) : (
    <span className="cover cover-empty" />
  )
  return (
    <td className="cover-cell">
      {spotifyId ? (
        <a
          href={`https://open.spotify.com/album/${spotifyId}`}
          target="_blank"
          rel="noopener noreferrer"
          title="Open in Spotify"
        >
          {img}
        </a>
      ) : (
        img
      )}
    </td>
  )
}

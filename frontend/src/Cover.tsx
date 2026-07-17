// Small album-art thumbnail cell (§8e). Art is served from the API at /art/<id>; `hasArt`
// tells us whether a blob exists so we show a quiet placeholder rather than a broken image.
export function Cover({ id, hasArt }: { id: number; hasArt: boolean }) {
  return (
    <td className="cover-cell">
      {hasArt ? (
        <img className="cover" src={`/art/${id}`} alt="" loading="lazy" />
      ) : (
        <span className="cover cover-empty" />
      )}
    </td>
  )
}

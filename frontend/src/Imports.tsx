import { useCallback, useEffect, useState } from 'react'

type Item = {
  id: number
  source: string
  name: string
  matched_album_id: number | null
  matched: string | null
}

export function Imports({ onChange }: { onChange?: () => void }) {
  const [items, setItems] = useState<Item[] | null>(null)

  useEffect(() => {
    fetch('/imports')
      .then((r) => r.json())
      .then(setItems)
      .catch(() => setItems([]))
  }, [])

  const runImport = useCallback(
    (id: number) => {
      setItems((list) => {
        if (!list) return list
        fetch(`/imports/${id}/import`, { method: 'POST' }).then(() => onChange?.())
        return list.filter((it) => it.id !== id)
      })
    },
    [onChange],
  )

  if (!items) return <p>Loading…</p>
  if (items.length === 0) return <p>No downloads to import.</p>

  return (
    <table>
      <tbody>
        {items.map((it) => (
          <tr key={it.id}>
            <td className="muted">{it.source}</td>
            <td>{it.name}</td>
            <td>{it.matched ?? <span className="muted">no match</span>}</td>
            <td>
              <button type="button" onClick={() => runImport(it.id)}>
                Import
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

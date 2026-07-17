import { useEffect, useState } from 'react'

type Counts = {
  releases: number
  decide: number
  acquire: number
  import: number
  owned: number
  dismissed: number
}

// One tile per worklist section, in the same order and wording as the page below.
const TILES: { key: keyof Counts; label: string }[] = [
  { key: 'releases', label: 'releases' },
  { key: 'decide', label: 'decide' },
  { key: 'acquire', label: 'acquire' },
  { key: 'import', label: 'import' },
  { key: 'owned', label: 'owned' },
  { key: 'dismissed', label: 'dismissed' },
]

export function Dashboard({ refreshKey = 0 }: { refreshKey?: number }) {
  const [counts, setCounts] = useState<Counts | null>(null)

  useEffect(() => {
    fetch('/dashboard')
      .then((r) => r.json())
      .then(setCounts)
      .catch(() => setCounts(null))
  }, [refreshKey])

  if (!counts) return null

  return (
    <div className="dashboard">
      {TILES.map((t) => (
        <span key={t.key} className="stat">
          <b>{counts[t.key]}</b> {t.label}
        </span>
      ))}
    </div>
  )
}

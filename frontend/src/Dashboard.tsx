import { useEffect, useState } from 'react'

type Counts = {
  decide: number
  acquire: number
  owned: number
  dismissed: number
  saved: number
}

const TILES: { key: keyof Counts; label: string }[] = [
  { key: 'decide', label: 'to judge' },
  { key: 'acquire', label: 'to buy' },
  { key: 'owned', label: 'owned' },
]

export function Dashboard() {
  const [counts, setCounts] = useState<Counts | null>(null)

  useEffect(() => {
    fetch('/dashboard')
      .then((r) => r.json())
      .then(setCounts)
      .catch(() => setCounts(null))
  }, [])

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

import { useEffect, useState } from 'react'

type Counts = {
  releases: number
  decide: number
  acquire: number
  import: number
  owned: number
  dismissed: number
}

export type Section = 'all' | keyof Counts

// One tile per worklist section, in the same order and wording as the page below.
const TILES: { key: keyof Counts; label: string }[] = [
  { key: 'releases', label: 'releases' },
  { key: 'decide', label: 'decide' },
  { key: 'acquire', label: 'acquire' },
  { key: 'import', label: 'import' },
  { key: 'owned', label: 'owned' },
  { key: 'dismissed', label: 'dismissed' },
]

type Props = {
  refreshKey?: number
  active?: Section
  onSelect?: (s: Section) => void
}

export function Dashboard({ refreshKey = 0, active = 'all', onSelect }: Props) {
  const [counts, setCounts] = useState<Counts | null>(null)

  // biome-ignore lint/correctness/useExhaustiveDependencies: refreshKey is a manual refetch trigger
  useEffect(() => {
    fetch('/dashboard')
      .then((r) => r.json())
      .then(setCounts)
      .catch(() => setCounts(null))
  }, [refreshKey])

  if (!counts) return null

  return (
    <div className="dashboard">
      <button
        type="button"
        className={active === 'all' ? 'stat active' : 'stat'}
        onClick={() => onSelect?.('all')}
      >
        all
      </button>
      {TILES.map((t) => (
        <button
          key={t.key}
          type="button"
          className={active === t.key ? 'stat active' : 'stat'}
          onClick={() => onSelect?.(t.key)}
        >
          <b>{counts[t.key]}</b> {t.label}
        </button>
      ))}
    </div>
  )
}

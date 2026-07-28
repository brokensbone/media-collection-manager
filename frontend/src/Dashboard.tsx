import { useEffect, useState } from 'react'

type Counts = {
  releases: number
  decide: number
  acquire: number
  import: number
  tasks: number
  owned: number
  dismissed: number
}

export type Section = 'all' | keyof Counts

// The counts payload also carries cold-start resolution progress, which isn't a section.
type Dash = Counts & { resolved: number; unresolved: number }

// One tile per worklist section, in the same order and wording as the page below.
const TILES: { key: keyof Counts; label: string }[] = [
  { key: 'releases', label: 'releases' },
  { key: 'decide', label: 'decide' },
  { key: 'acquire', label: 'acquire' },
  { key: 'import', label: 'import' },
  { key: 'tasks', label: 'tasks' },
  { key: 'owned', label: 'owned' },
  { key: 'dismissed', label: 'dismissed' },
]

type Props = {
  refreshKey?: number
  active?: Section
  onSelect?: (s: Section) => void
}

export function Dashboard({ refreshKey = 0, active = 'all', onSelect }: Props) {
  const [counts, setCounts] = useState<Dash | null>(null)

  // biome-ignore lint/correctness/useExhaustiveDependencies: refreshKey is a manual refetch trigger
  useEffect(() => {
    fetch('/dashboard')
      .then((r) => r.json())
      .then(setCounts)
      .catch(() => setCounts(null))
  }, [refreshKey])

  // Render the panel immediately with a static layout; only the numbers fill in once the fetch
  // lands, so the page doesn't jump when the (slightly slow) counts arrive.
  return (
    <>
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
            <b>{counts ? counts[t.key] : '·'}</b> {t.label}
          </button>
        ))}
      </div>
      {counts && counts.unresolved > 0 && (
        <div className="muted resolving">
          Resolving to MusicBrainz: {counts.resolved}/{counts.resolved + counts.unresolved} albums
          matched
        </div>
      )}
    </>
  )
}

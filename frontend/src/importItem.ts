// The shape the /imports, /imports/tasks and /imports/archive endpoints return. Shared by the
// Import worklist, the Tasks view and the completed archive.
export type ImportState = 'detected' | 'queued' | 'importing' | 'imported' | 'skipped' | 'failed'

export type ImportItem = {
  id: number
  source: string
  name: string
  media_kind: 'music' | 'tv' | 'film' | 'workspace' | 'unknown'
  import_target: 'beets' | 'tv' | 'film' | 'workspace' | 'review'
  classification_detail: string | null
  destination_path: string | null
  state: ImportState
  matched_album_id: number | null
  matched: string | null
  matched_owned: boolean
  missing: boolean
  error_detail: string | null
  updated_at: string | null
  created_at: string | null
}

export function labelKind(kind: ImportItem['media_kind']): string {
  if (kind === 'tv') return 'TV'
  if (kind === 'film') return 'Film'
  if (kind === 'music') return 'Music'
  if (kind === 'workspace') return 'Workspace'
  return 'Unknown'
}

export function whenLabel(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const today = new Date().toDateString() === d.toDateString()
  return today ? d.toLocaleTimeString() : d.toLocaleString()
}

// A discovery-day heading for grouping the Import list: "Today" / "Yesterday" / a plain date.
export function dayLabel(iso: string | null): string {
  if (!iso) return 'Unknown date'
  const d = new Date(iso)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

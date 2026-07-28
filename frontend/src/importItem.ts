// The shape the /imports, /imports/tasks and /imports/archive endpoints return. Shared by the
// Import worklist, the Tasks view and the completed archive.
export type ImportState = 'detected' | 'queued' | 'importing' | 'imported' | 'skipped' | 'failed'

export type ImportItem = {
  id: number
  source: string
  name: string
  media_kind: 'music' | 'tv' | 'film' | 'unknown'
  import_target: 'beets' | 'tv' | 'film' | 'review'
  classification_detail: string | null
  destination_path: string | null
  state: ImportState
  matched_album_id: number | null
  matched: string | null
  matched_owned: boolean
  missing: boolean
  error_detail: string | null
  updated_at: string | null
}

export function labelKind(kind: ImportItem['media_kind']): string {
  if (kind === 'tv') return 'TV'
  if (kind === 'film') return 'Film'
  if (kind === 'music') return 'Music'
  return 'Unknown'
}

export function whenLabel(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const today = new Date().toDateString() === d.toDateString()
  return today ? d.toLocaleTimeString() : d.toLocaleString()
}

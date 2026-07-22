import { useEffect, useRef, useState } from 'react'

// Live tail of what the worker is doing, one row per item it processes (resolve, own, import,
// …). Polls /events?after=<cursor> every ~1.5s and appends; newest shown first, DOM capped.
type Event = {
  id: number
  created_at: string
  job: string
  type: string
  message: string
  album_id: number | null
}

const MAX_ROWS = 200
const POLL_MS = 1500

export function Activity() {
  const [events, setEvents] = useState<Event[]>([])
  const cursor = useRef<number | null>(null)

  useEffect(() => {
    let stopped = false
    async function tick() {
      const url = cursor.current == null ? '/events' : `/events?after=${cursor.current}`
      try {
        const rows: Event[] = await fetch(url).then((r) => r.json())
        if (!stopped && rows.length) {
          cursor.current = rows[rows.length - 1].id
          setEvents((prev) => [...prev, ...rows].slice(-MAX_ROWS))
        }
      } catch {
        // a poll blip is fine — the next tick retries from the same cursor
      }
    }
    tick()
    const handle = setInterval(tick, POLL_MS)
    return () => {
      stopped = true
      clearInterval(handle)
    }
  }, [])

  if (events.length === 0) return <p className="muted">No worker activity yet.</p>

  return (
    <table className="activity">
      <tbody>
        {[...events].reverse().map((e) => (
          <tr key={e.id} className={`ev ev-${e.type}`}>
            <td className="ev-time muted">{new Date(e.created_at).toLocaleTimeString()}</td>
            <td>
              <span className="ev-job">{e.job}</span>
            </td>
            <td>{e.message}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

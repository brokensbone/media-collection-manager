import { useCallback, useEffect, useState } from 'react'

type Torrent = {
  id: number
  name: string
  state: string
  matched: string | null
  has_audio: boolean | null
}

type Check = { ok: boolean; detail: string }
type TestReport = { api: Check; ssh: Check }

export function Transmission() {
  const [torrents, setTorrents] = useState<Torrent[] | null>(null)
  const [report, setReport] = useState<TestReport | null>(null)
  const [testing, setTesting] = useState(false)

  useEffect(() => {
    fetch('/transmission/torrents')
      .then((r) => r.json())
      .then(setTorrents)
      .catch(() => setTorrents([]))
  }, [])

  const runTest = useCallback(() => {
    setTesting(true)
    setReport(null)
    fetch('/transmission/test', { method: 'POST' })
      .then((r) => r.json())
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setTesting(false))
  }, [])

  return (
    <>
      <section>
        <h2>Connection</h2>
        <p className="muted">
          Check the app can reach Transmission's RPC API and SSH to the seedbox.
        </p>
        <button type="button" onClick={runTest} disabled={testing}>
          {testing ? 'Testing…' : 'Test connection'}
        </button>
        {report && (
          <div className="checks">
            <CheckLine label="API" check={report.api} />
            <CheckLine label="SSH" check={report.ssh} />
          </div>
        )}
      </section>

      <section>
        <h2>Torrents seen</h2>
        {!torrents ? (
          <p>Loading…</p>
        ) : torrents.length === 0 ? (
          <p className="muted">
            No torrents seen yet — connect Transmission and the poller will fill this in.
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>name</th>
                <th>kind</th>
                <th>state</th>
                <th>matched</th>
              </tr>
            </thead>
            <tbody>
              {torrents.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td className="muted">{kind(t.has_audio)}</td>
                  <td className="muted">{t.state}</td>
                  <td>{t.matched ?? <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  )
}

function kind(hasAudio: boolean | null): string {
  if (hasAudio === false) return 'non-audio'
  if (hasAudio) return 'audio'
  return '—'
}

function CheckLine({ label, check }: { label: string; check: Check }) {
  return (
    <div>
      <strong>{label}:</strong> {check.ok ? '✓ ok' : '✗ failed'}{' '}
      <span className="muted">{check.detail}</span>
    </div>
  )
}

import { useCallback, useEffect, useState } from 'react'

type Torrent = {
  id: number
  name: string
  media_kind: 'music' | 'tv' | 'film' | 'unknown'
  import_target: 'beets' | 'tv' | 'film' | 'review'
  classification_detail: string | null
  destination_path: string | null
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
            <colgroup>
              <col />
              <col className="c-kind" />
              <col />
              <col className="c-state" />
              <col className="c-matched" />
            </colgroup>
            <thead>
              <tr>
                <th>name</th>
                <th>kind</th>
                <th>destination</th>
                <th>state</th>
                <th>matched</th>
              </tr>
            </thead>
            <tbody>
              {torrents.map((t) => (
                <tr key={t.id}>
                  <td>
                    <div>{t.name}</div>
                    {t.classification_detail && (
                      <div className="muted">{t.classification_detail}</div>
                    )}
                  </td>
                  <td className="muted">{kind(t)}</td>
                  <td className="muted">{t.destination_path ?? '—'}</td>
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

function kind(torrent: Torrent): string {
  if (torrent.media_kind === 'unknown' && torrent.has_audio === false) return 'non-media'
  if (torrent.media_kind === 'music') return 'music'
  if (torrent.media_kind === 'tv') return 'tv'
  if (torrent.media_kind === 'film') return 'film'
  return 'unknown'
}

function CheckLine({ label, check }: { label: string; check: Check }) {
  return (
    <div>
      <strong>{label}:</strong> {check.ok ? '✓ ok' : '✗ failed'}{' '}
      <span className="muted">{check.detail}</span>
    </div>
  )
}

import './styles.css'
import { type ReactNode, useCallback, useEffect, useState } from 'react'
import { Acquire } from './Acquire'
import { Dashboard, type Section } from './Dashboard'
import { Decide } from './Decide'
import { Guide } from './Guide'
import { Imports } from './Imports'
import { Library } from './Library'
import { Releases } from './Releases'
import { SpotifyStatus } from './SpotifyStatus'
import { Transmission } from './Transmission'

type View = 'app' | 'guide' | 'transmission'

const SECTIONS: Section[] = ['all', 'releases', 'decide', 'acquire', 'import', 'owned', 'dismissed']

// The active tab lives in the URL hash (#guide, #transmission, #acquire, …) so a refresh or
// a shared link restores the same view.
function readHash(): { view: View; section: Section } {
  const h = window.location.hash.replace(/^#/, '')
  if (h === 'guide') return { view: 'guide', section: 'all' }
  if (h === 'transmission') return { view: 'transmission', section: 'all' }
  if ((SECTIONS as string[]).includes(h)) return { view: 'app', section: h as Section }
  return { view: 'app', section: 'all' }
}

export default function App() {
  const [view, setView] = useState<View>(() => readHash().view)
  const [section, setSection] = useState<Section>(() => readHash().section)
  const [query, setQuery] = useState('')

  useEffect(() => {
    const target = view === 'app' ? section : view
    if (window.location.hash.replace(/^#/, '') !== target) window.location.hash = target
  }, [view, section])

  useEffect(() => {
    function onHash() {
      const r = readHash()
      setView(r.view)
      setSection(r.section)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  // Any worklist action bumps this; the count/browse views refetch when it changes.
  const [refresh, setRefresh] = useState(0)
  const bump = useCallback(() => setRefresh((n) => n + 1), [])

  const sections: { key: Section; heading: string; node: ReactNode }[] = [
    { key: 'releases', heading: 'Releases', node: <Releases onChange={bump} query={query} /> },
    { key: 'decide', heading: 'Decide', node: <Decide onChange={bump} query={query} /> },
    { key: 'acquire', heading: 'Acquire', node: <Acquire onChange={bump} query={query} /> },
    { key: 'import', heading: 'Import', node: <Imports onChange={bump} query={query} /> },
    {
      key: 'owned',
      heading: 'Owned',
      node: <Library state="owned" refreshKey={refresh} query={query} />,
    },
    {
      key: 'dismissed',
      heading: 'Dismissed',
      node: <Library state="dismissed" refreshKey={refresh} query={query} />,
    },
  ]

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">wantlist</span>
        <div className="topbar-right">
          <button
            type="button"
            className="linklike"
            onClick={() => setView(view === 'guide' ? 'app' : 'guide')}
          >
            {view === 'guide' ? 'Dashboard' : 'Guide'}
          </button>
          <button
            type="button"
            className="linklike"
            onClick={() => setView(view === 'transmission' ? 'app' : 'transmission')}
          >
            {view === 'transmission' ? 'Dashboard' : 'Transmission'}
          </button>
          <SpotifyStatus />
        </div>
      </header>
      {view === 'guide' ? (
        <Guide />
      ) : view === 'transmission' ? (
        <Transmission />
      ) : (
        <>
          <Dashboard refreshKey={refresh} active={section} onSelect={setSection} />
          <input
            type="search"
            className="filter"
            placeholder="filter by artist or title…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {sections
            .filter((s) => section === 'all' || s.key === section)
            .map((s) => (
              <section key={s.key}>
                <h2>{s.heading}</h2>
                {s.node}
              </section>
            ))}
        </>
      )}
    </div>
  )
}

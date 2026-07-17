import './styles.css'
import { type ReactNode, useCallback, useState } from 'react'
import { Acquire } from './Acquire'
import { Dashboard, type Section } from './Dashboard'
import { Decide } from './Decide'
import { Guide } from './Guide'
import { Imports } from './Imports'
import { Library } from './Library'
import { Releases } from './Releases'
import { SpotifyStatus } from './SpotifyStatus'

type View = 'app' | 'guide'

export default function App() {
  const [view, setView] = useState<View>('app')
  const [section, setSection] = useState<Section>('all')
  // Any worklist action bumps this; the count/browse views refetch when it changes.
  const [refresh, setRefresh] = useState(0)
  const bump = useCallback(() => setRefresh((n) => n + 1), [])

  const sections: { key: Section; heading: string; node: ReactNode }[] = [
    { key: 'releases', heading: 'Releases', node: <Releases onChange={bump} /> },
    { key: 'decide', heading: 'Decide', node: <Decide onChange={bump} /> },
    { key: 'acquire', heading: 'Acquire', node: <Acquire onChange={bump} /> },
    { key: 'import', heading: 'Import', node: <Imports onChange={bump} /> },
    { key: 'owned', heading: 'Owned', node: <Library state="owned" refreshKey={refresh} /> },
    {
      key: 'dismissed',
      heading: 'Dismissed',
      node: <Library state="dismissed" refreshKey={refresh} />,
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
          <SpotifyStatus />
        </div>
      </header>
      {view === 'guide' ? (
        <Guide />
      ) : (
        <>
          <Dashboard refreshKey={refresh} active={section} onSelect={setSection} />
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

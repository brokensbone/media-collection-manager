import './styles.css'
import { useCallback, useState } from 'react'
import { Acquire } from './Acquire'
import { Dashboard } from './Dashboard'
import { Decide } from './Decide'
import { Guide } from './Guide'
import { Imports } from './Imports'
import { Library } from './Library'
import { Releases } from './Releases'
import { SpotifyStatus } from './SpotifyStatus'

type View = 'app' | 'guide'

export default function App() {
  const [view, setView] = useState<View>('app')
  // Any worklist action bumps this; the count/browse views refetch when it changes.
  const [refresh, setRefresh] = useState(0)
  const bump = useCallback(() => setRefresh((n) => n + 1), [])

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
          <Dashboard refreshKey={refresh} />
          <h2>Releases</h2>
          <Releases onChange={bump} />
          <h2>Decide</h2>
          <Decide onChange={bump} />
          <h2>Acquire</h2>
          <Acquire onChange={bump} />
          <h2>Import</h2>
          <Imports onChange={bump} />
          <h2>Owned</h2>
          <Library state="owned" refreshKey={refresh} />
          <h2>Dismissed</h2>
          <Library state="dismissed" refreshKey={refresh} />
        </>
      )}
    </div>
  )
}

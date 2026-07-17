import './styles.css'
import { useState } from 'react'
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
          <Dashboard />
          <h2>Releases</h2>
          <Releases />
          <h2>Decide</h2>
          <Decide />
          <h2>Acquire</h2>
          <Acquire />
          <h2>Import</h2>
          <Imports />
          <h2>Owned</h2>
          <Library state="owned" />
          <h2>Dismissed</h2>
          <Library state="dismissed" />
        </>
      )}
    </div>
  )
}

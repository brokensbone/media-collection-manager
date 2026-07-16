import './styles.css'
import { Acquire } from './Acquire'
import { Dashboard } from './Dashboard'
import { Decide } from './Decide'
import { Library } from './Library'
import { Releases } from './Releases'
import { SpotifyStatus } from './SpotifyStatus'

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">wantlist</span>
        <SpotifyStatus />
      </header>
      <Dashboard />
      <h2>Releases</h2>
      <Releases />
      <h2>Decide</h2>
      <Decide />
      <h2>Acquire</h2>
      <Acquire />
      <h2>Owned</h2>
      <Library state="owned" />
      <h2>Dismissed</h2>
      <Library state="dismissed" />
    </div>
  )
}

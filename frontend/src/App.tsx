import { Acquire } from './Acquire'
import { Decide } from './Decide'
import { Library } from './Library'
import { SpotifyStatus } from './SpotifyStatus'

export default function App() {
  return (
    <>
      <h1>wantlist</h1>
      <SpotifyStatus />
      <h2>Decide</h2>
      <Decide />
      <h2>Acquire</h2>
      <Acquire />
      <h2>Library</h2>
      <Library />
    </>
  )
}

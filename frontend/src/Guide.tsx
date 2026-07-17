export function Guide() {
  return (
    <div className="guide">
      <h1>How wantlist works</h1>
      <p>
        wantlist is a smart want-list for music. It watches the albums you save on Spotify, checks
        them against what you already own in your beets library, and turns them into small,
        clearable to-do lists — so the album you meant to buy doesn't quietly get forgotten. It is{' '}
        <strong>not a recommender</strong>: everything here started with you.
      </p>

      <h2>The loop</h2>
      <p className="funnel">saved → decide → wanted → acquire → owned</p>
      <p>
        An album you save on Spotify lands in <strong>saved</strong>. Once you've had a chance to
        live with it, it surfaces in <strong>Decide</strong>, where you keep it (→{' '}
        <strong>wanted</strong>) or drop it (→ <strong>dismissed</strong>). Wanted albums wait in{' '}
        <strong>Acquire</strong> until you buy and import them, at which point they become{' '}
        <strong>owned</strong>. Two side entrances: new releases from artists you keep show up as{' '}
        <strong>suggested</strong> (see Releases), and anything you drop goes to{' '}
        <strong>dismissed</strong> so it won't nag you again.
      </p>

      <h2>Decide</h2>
      <p>
        Your triage queue. An album shows up here when it's worth a verdict — either because it's
        been <strong>forgotten</strong> (saved a while ago and barely played) or because you've
        actually <strong>listened</strong> to it a few times. For each one:
      </p>
      <ul>
        <li>
          <strong>Keep</strong> — you want it: moves to <strong>wanted</strong> and joins Acquire.
        </li>
        <li>
          <strong>Drop</strong> — not for you: moves to <strong>dismissed</strong>.
        </li>
        <li>
          <strong>Snooze</strong> — not sure yet: hides it for a while, then it comes back.
        </li>
      </ul>

      <h2>Acquire</h2>
      <p>
        Your buy list — the albums you've decided you want but don't own yet. Each has a{' '}
        <strong>Buy on Bandcamp</strong> search link. When you've ordered something, hit{' '}
        <strong>Mark ordered</strong> and it drops out of the list (you can undo that).
      </p>
      <p>
        When an album lands in your library, wantlist normally notices on its own. But editions
        differ — you might own the deluxe when Spotify had the standard — so{' '}
        <strong>Mark owned…</strong> lets you link a want directly to the matching album in your
        library. It even suggests likely matches so it's one click. If a want looks like something
        you already own, Acquire flags it (<em>possibly owned</em>) so you don't re-buy. This is why
        the loop can always be closed, even for albums MusicBrainz doesn't know.
      </p>

      <h2>Releases</h2>
      <p>
        New albums from artists you've kept before. Nothing that existed when an artist was first
        watched shows up here — only genuinely new releases. For each you can <strong>Save</strong>{' '}
        it (into the normal saved → decide flow) or send it straight to <strong>Want</strong> if you
        already know you want it.
      </p>

      <h2>Import</h2>
      <p>
        Where finished downloads wait to be brought into your library. Completed Transmission
        torrents and files dropped into the watch folder (e.g. a Bandcamp zip) both appear here,
        matched to the want they satisfy where possible. One click on <strong>Import</strong> pulls
        the files in, adds them to beets, and the album flips to <strong>owned</strong> on its own.
        Downloads with no matching want can still be imported — they just become owned with no prior
        want.
      </p>

      <h2>Staying connected to Spotify</h2>
      <p>
        The status in the top bar tells you whether wantlist is connected to Spotify and roughly
        when you'll need to <strong>reconnect</strong> (about every six months). This matters: if
        the connection lapses, every worklist quietly stops filling — no new saves, plays, or
        releases come in — so reconnect promptly when it asks.
      </p>

      <h2>How it works behind the scenes</h2>
      <p>
        wantlist checks Spotify on a schedule for new saves, recent plays, and new releases from
        your artists. Ownership isn't something you set — it's <em>derived</em>: wantlist regularly
        compares your want-list against your beets library and marks matches as owned (this is
        called reconcile). Nothing here is a recommendation engine and nothing is bought
        automatically — it only ever surfaces choices for you to make.
      </p>
    </div>
  )
}

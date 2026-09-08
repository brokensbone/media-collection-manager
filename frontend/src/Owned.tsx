import { useEffect, useState } from "react";
import { Cover } from "./Cover";
import { matchesQuery } from "./filter";

// Owned is the beets library itself — everything you actually own — with Spotify overlaid where
// it lines up (cover art + out-links). Unmatched albums still show.
type OwnedAlbum = {
	beets_id: string;
	artist: string;
	title: string;
	album_id: number | null;
	has_art: boolean;
	on_spotify: boolean;
	spotify_id: string | null;
	mb_releasegroup_id: string | null;
};

// A generic chain-link glyph for the shareable permalink pill.
function LinkIcon() {
	return (
		<svg
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth="2"
			strokeLinecap="round"
			strokeLinejoin="round"
			aria-hidden="true"
		>
			<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
			<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
		</svg>
	);
}

// The Spotify wordmark glyph (green circle with three curves) for the Spotify pill.
function SpotifyIcon() {
	return (
		<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
			<path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.5 17.3a.75.75 0 0 1-1.03.25c-2.82-1.72-6.37-2.11-10.55-1.16a.75.75 0 1 1-.33-1.46c4.57-1.04 8.5-.59 11.66 1.34.36.22.47.68.25 1.03zm1.47-3.27a.94.94 0 0 1-1.29.31c-3.23-1.98-8.15-2.56-11.97-1.4a.94.94 0 1 1-.54-1.8c4.36-1.32 9.78-.68 13.49 1.6.44.27.58.85.31 1.29zm.13-3.4C15.36 8.4 8.9 8.16 5.2 9.29a1.12 1.12 0 1 1-.65-2.15c4.25-1.29 11.38-1.04 15.85 1.61a1.12 1.12 0 1 1-1.15 1.93z" />
		</svg>
	);
}

export function Owned({
	refreshKey = 0,
	query = "",
}: {
	refreshKey?: number;
	query?: string;
}) {
	const [albums, setAlbums] = useState<OwnedAlbum[] | null>(null);
	// The linked/highlighted album is carried in the URL (#owned?sel=<beets_id>) so a specific
	// library entry can be shared by link — e.g. to point at one of a pair of duplicates.
	const [sel, setSel] = useState<string | null>(() => selFromHash());

	// biome-ignore lint/correctness/useExhaustiveDependencies: refreshKey is a manual refetch trigger
	useEffect(() => {
		fetch("/owned")
			.then((r) => r.json())
			.then(setAlbums)
			.catch(() => setAlbums([]));
	}, [refreshKey]);

	// Follow the URL so a shared #owned?sel=… link (or back/forward) highlights that row.
	useEffect(() => {
		const onHash = () => setSel(selFromHash());
		window.addEventListener("hashchange", onHash);
		return () => window.removeEventListener("hashchange", onHash);
	}, []);

	// Bring a linked album into view once its row has rendered.
	useEffect(() => {
		if (!sel || !albums) return;
		document
			.getElementById(`owned-${sel}`)
			?.scrollIntoView?.({ block: "center" });
	}, [sel, albums]);

	if (!albums) return <p>Loading…</p>;
	if (albums.length === 0) return <p>Nothing here.</p>;

	const shown = albums.filter((a) =>
		matchesQuery(`${a.artist} ${a.title}`, query),
	);

	return (
		<table className="mobile-card-table">
			<colgroup>
				<col className="c-cover" />
				<col className="c-artist" />
				<col />
				<col className="c-aux" />
			</colgroup>
			<tbody>
				{shown.map((a) => (
					<tr
						key={a.beets_id}
						id={`owned-${a.beets_id}`}
						className={sel === a.beets_id ? "linked" : undefined}
					>
						<Cover
							id={a.album_id ?? 0}
							hasArt={a.has_art}
							spotifyId={a.spotify_id}
						/>
						<td>{a.artist}</td>
						<td>{a.title}</td>
						<td className="links">
							<div className="pill-row">
								<a
									className="pill"
									href={`#owned?sel=${encodeURIComponent(a.beets_id)}`}
									title="Link to this album"
									aria-label="Link to this album"
								>
									<LinkIcon />
								</a>
								{a.spotify_id ? (
									<a
										className="pill pill-sp"
										href={`https://open.spotify.com/album/${a.spotify_id}`}
										target="_blank"
										rel="noopener noreferrer"
										title="Open on Spotify"
										aria-label="Open on Spotify"
									>
										<SpotifyIcon />
									</a>
								) : null}
								{a.mb_releasegroup_id ? (
									<a
										className="pill pill-mb"
										href={`https://musicbrainz.org/release-group/${a.mb_releasegroup_id}`}
										target="_blank"
										rel="noopener noreferrer"
										title="Open on MusicBrainz"
										aria-label="Open on MusicBrainz"
									>
										MB
									</a>
								) : null}
							</div>
						</td>
					</tr>
				))}
			</tbody>
		</table>
	);
}

// The `sel` param from a #owned?sel=… URL, or null.
function selFromHash(): string | null {
	const query = window.location.hash.split("?")[1] ?? "";
	return new URLSearchParams(query).get("sel");
}

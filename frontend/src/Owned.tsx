import "./pages-library.css";
import { useEffect } from "react";
import { Cover } from "./Cover";
import { useHashParam } from "./hashState";
import { LinkIcon, SpotifyIcon } from "./icons";
import { libraryState, useLibraryList } from "./Library";
import { FilterBox, PageHeader } from "./ui";

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

export function Owned({
	refreshKey = 0,
	query = "",
}: {
	refreshKey?: number;
	query?: string;
}) {
	const { items, failed, load, shown, count, sortControl } =
		useLibraryList<OwnedAlbum>("/owned", refreshKey, query);
	// The linked/highlighted album is carried in the URL (#owned?sel=<beets_id>) so a specific
	// library entry can be shared by link — e.g. to point at one of a pair of duplicates.
	const [sel] = useHashParam("sel");

	// Bring a linked album into view once its row has rendered.
	useEffect(() => {
		if (!sel || !items) return;
		document
			.getElementById(`owned-${sel}`)
			?.scrollIntoView?.({ block: "center" });
	}, [sel, items]);

	const body = libraryState(
		items,
		failed,
		shown.length,
		query,
		"owned albums",
		load,
	) ?? (
		<table className="rows compact library-table owned-table">
			<colgroup>
				<col className="c-cover" />
				<col className="c-artist" />
				<col />
				<col className="c-links" />
			</colgroup>
			<thead>
				<tr>
					<th scope="col">
						<span className="sr-only">Cover</span>
					</th>
					<th scope="col">Artist</th>
					<th scope="col">Title</th>
					<th scope="col">Links</th>
				</tr>
			</thead>
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
							size={24}
						/>
						<td className="cell-primary">{a.artist}</td>
						<td className="cell-secondary">{a.title}</td>
						<td className="cell-actions">
							<div className="pill-row">
								<a
									className="pill"
									href={`#owned?sel=${encodeURIComponent(a.beets_id)}`}
									title="Link to this album"
									aria-label="Link to this album"
								>
									<LinkIcon size={13} />
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
										<SpotifyIcon size={13} />
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

	return (
		<>
			<PageHeader title="Owned" count={count} filter={<FilterBox />}>
				{sortControl}
			</PageHeader>
			{body}
		</>
	);
}

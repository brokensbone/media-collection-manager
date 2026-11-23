// Small album-art thumbnail cell (§8e). Art is served from the API at /art/<id>; `hasArt`
// tells us whether a blob exists so we show a quiet placeholder rather than a broken image.
// With `spotifyId`, the cover links to the album on Spotify, opening in a new tab.
export function Cover({
	id,
	hasArt,
	spotifyId,
	size = 32,
}: {
	id: number;
	hasArt: boolean;
	spotifyId?: string | null;
	size?: 24 | 32;
}) {
	const cls = size === 24 ? "cover cover-24" : "cover";
	const img = hasArt ? (
		<img
			className={cls}
			src={`/art/${id}`}
			alt=""
			width={size}
			height={size}
			loading="lazy"
		/>
	) : (
		<span className={`${cls} cover-empty`} />
	);
	return (
		<td className="cell-cover">
			{spotifyId ? (
				<a
					className="cover-link"
					href={`https://open.spotify.com/album/${spotifyId}`}
					target="_blank"
					rel="noopener noreferrer"
					title="Open in Spotify"
					aria-label="Open in Spotify"
				>
					{img}
				</a>
			) : (
				img
			)}
		</td>
	);
}

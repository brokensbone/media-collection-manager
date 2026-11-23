import "./pages-worklists.css";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { fetchJson } from "./api";
import { Cover } from "./Cover";
import { matchesQuery } from "./filter";
import { useRowKeys } from "./keys";
import {
	Badge,
	EmptyState,
	ErrorState,
	FilterBox,
	Kbd,
	ListHints,
	Loading,
	NoMatches,
	PageHeader,
	useAnnounceCount,
} from "./ui";

type Item = {
	id: number;
	artist: string;
	title: string;
	has_art: boolean;
	spotify_id: string | null;
	album_type: string | null;
};
type Action = "save" | "want" | "dismiss";

export function Releases({
	onChange,
	query = "",
	limit,
}: {
	onChange?: () => void;
	query?: string;
	limit?: number;
}) {
	const [items, setItems] = useState<Item[] | null>(null);
	const [failed, setFailed] = useState(false);
	const full = limit == null;

	const load = useCallback(() => {
		setFailed(false);
		fetchJson<Item[]>("/releases").then(setItems, () => setFailed(true));
	}, []);
	useEffect(load, [load]);

	const act = useCallback(
		(id: number, action: Action) => {
			fetch(`/albums/${id}/${action}`, { method: "POST" }).then(() =>
				onChange?.(),
			);
			setItems((list) => (list ? list.filter((it) => it.id !== id) : list));
		},
		[onChange],
	);

	const matched = (items ?? []).filter((it) =>
		matchesQuery(`${it.artist} ${it.title}`, query),
	);
	const shown = matched.slice(0, limit);
	const { rowProps } = useRowKeys({
		count: shown.length,
		enabled: full,
		actions: {
			s: (i) => act(shown[i].id, "save"),
			w: (i) => act(shown[i].id, "want"),
			d: (i) => act(shown[i].id, "dismiss"),
		},
	});
	useAnnounceCount(
		shown.length,
		items?.length ?? 0,
		full && items != null && query !== "",
	);

	let body: ReactNode;
	if (!items)
		body = failed ? (
			<ErrorState what="releases" onRetry={load} />
		) : (
			<Loading rows={full ? 6 : 3} />
		);
	else if (items.length === 0)
		body = full ? (
			<EmptyState title="No new releases." />
		) : (
			<p className="state-inline">Nothing waiting.</p>
		);
	else if (shown.length === 0)
		body = full ? (
			<NoMatches query={query} what="releases" />
		) : (
			<p className="state-inline">No matches for “{query}”.</p>
		);
	else
		body = (
			<>
				<table className="rows worklist">
					<colgroup>
						<col className="c-cover" />
						<col className="c-artist" />
						<col />
						<col className="c-wl-actions" />
					</colgroup>
					{full && (
						<thead>
							<tr>
								<th scope="col">
									<span className="sr-only">Cover</span>
								</th>
								<th scope="col">Artist</th>
								<th scope="col">Title</th>
								<th scope="col">
									<span className="sr-only">Actions</span>
								</th>
							</tr>
						</thead>
					)}
					<tbody>
						{shown.map((it, i) => (
							<tr key={it.id} {...(full ? rowProps(i) : {})}>
								<Cover
									id={it.id}
									hasArt={it.has_art}
									spotifyId={it.spotify_id}
								/>
								<td className="cell-primary">{it.artist}</td>
								<td className="cell-secondary">
									{it.title}
									{it.album_type && <Badge>{it.album_type}</Badge>}
								</td>
								<td className="cell-actions">
									<div className="row-actions">
										<button
											type="button"
											className="btn-primary"
											onClick={() => act(it.id, "save")}
										>
											Save
											{full && <Kbd>s</Kbd>}
										</button>
										<button type="button" onClick={() => act(it.id, "want")}>
											Want
											{full && <Kbd>w</Kbd>}
										</button>
										<button
											type="button"
											className="btn-quiet"
											onClick={() => act(it.id, "dismiss")}
										>
											Dismiss
											{full && <Kbd>d</Kbd>}
										</button>
									</div>
								</td>
							</tr>
						))}
					</tbody>
				</table>
				{full && (
					<ListHints
						items={[
							["j/k", "move"],
							["s", "save"],
							["w", "want"],
							["d", "dismiss"],
						]}
					/>
				)}
			</>
		);

	if (!full) return body;
	return (
		<>
			<PageHeader
				title="Releases"
				count={
					items == null
						? undefined
						: query
							? `${shown.length} of ${items.length}`
							: items.length
				}
				filter={<FilterBox />}
			/>
			{body}
		</>
	);
}

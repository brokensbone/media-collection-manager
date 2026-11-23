import "./pages-library.css";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { fetchJson } from "./api";
import { Cover } from "./Cover";
import { matchesQuery } from "./filter";
import { useHashParam } from "./hashState";
import {
	EmptyState,
	ErrorState,
	FilterBox,
	Loading,
	NoMatches,
	PageHeader,
	Segmented,
	useAnnounceCount,
} from "./ui";

type Album = {
	id: number;
	artist: string;
	title: string;
	state: string;
	owned: boolean;
	has_art: boolean;
	spotify_id: string | null;
};

export type LibrarySort = "artist" | "title";

// Shared by Owned and Dismissed: one list fetch with the five states, the ?sort= order and the
// filter, so both pages behave the same.
export function useLibraryList<T extends { artist: string; title: string }>(
	url: string,
	refreshKey: number,
	query: string,
) {
	const [items, setItems] = useState<T[] | null>(null);
	const [failed, setFailed] = useState(false);
	const [sortParam, setSortParam] = useHashParam("sort");
	const sort: LibrarySort = sortParam === "title" ? "title" : "artist";

	// biome-ignore lint/correctness/useExhaustiveDependencies: refreshKey is a manual refetch trigger
	const load = useCallback(() => {
		setFailed(false);
		fetchJson<T[]>(url).then(setItems, () => setFailed(true));
	}, [url, refreshKey]);
	useEffect(load, [load]);

	const shown = (items ?? [])
		.filter((a) => matchesQuery(`${a.artist} ${a.title}`, query))
		.sort((a, b) =>
			sort === "title"
				? byText(a.title, b.title) || byText(a.artist, b.artist)
				: byText(a.artist, b.artist) || byText(a.title, b.title),
		);
	useAnnounceCount(shown.length, items?.length ?? 0, items != null && !!query);

	const count =
		items == null
			? undefined
			: query
				? `${shown.length} of ${items.length}`
				: items.length;

	const sortControl = (
		<div className="sort-control">
			<span className="sort-label" aria-hidden="true">
				Sort
			</span>
			<Segmented<LibrarySort>
				ariaLabel="Sort"
				value={sort}
				onChange={(v) =>
					setSortParam(v === "artist" ? null : v, { replace: true })
				}
				options={[
					{ value: "artist", label: "Artist" },
					{ value: "title", label: "Title" },
				]}
			/>
		</div>
	);

	return { items, failed, load, shown, count, sortControl };
}

function byText(a: string, b: string): number {
	return a.localeCompare(b, undefined, { sensitivity: "base", numeric: true });
}

// Picks the one state a library list is in, or null when the table should render.
export function libraryState(
	items: unknown[] | null,
	failed: boolean,
	shownCount: number,
	query: string,
	what: string,
	load: () => void,
): ReactNode | null {
	if (!items)
		return failed ? (
			<ErrorState what={what} onRetry={load} />
		) : (
			<Loading rows={8} compact />
		);
	if (items.length === 0) return <EmptyState title="Nothing here." />;
	if (shownCount === 0) return <NoMatches query={query} what={what} />;
	return null;
}

const TITLES: Record<string, string> = {
	dismissed: "Dismissed",
	owned: "Owned",
	saved: "Saved",
};

export function Library({
	state,
	refreshKey = 0,
	query = "",
}: {
	state?: string;
	refreshKey?: number;
	query?: string;
}) {
	const url = state ? `/albums?state=${state}` : "/albums";
	const { items, failed, load, shown, count, sortControl } =
		useLibraryList<Album>(url, refreshKey, query);
	const title = state ? (TITLES[state] ?? state) : "Albums";

	const body = libraryState(
		items,
		failed,
		shown.length,
		query,
		title.toLowerCase(),
		load,
	) ?? (
		<table className="rows compact library-table sticky-head">
			<colgroup>
				<col className="c-cover" />
				<col className="c-artist" />
				<col />
				{!state && <col className="c-state" />}
			</colgroup>
			<thead>
				<tr>
					<th scope="col">
						<span className="sr-only">Cover</span>
					</th>
					<th scope="col">Artist</th>
					<th scope="col">Title</th>
					{!state && <th scope="col">State</th>}
				</tr>
			</thead>
			<tbody>
				{shown.map((a) => (
					<tr key={a.id}>
						<Cover
							id={a.id}
							hasArt={a.has_art}
							spotifyId={a.spotify_id}
							size={24}
						/>
						<td className="cell-primary">{a.artist}</td>
						<td className="cell-secondary">{a.title}</td>
						{/* The state is redundant in a single-state view (Owned/Dismissed); only show it
                in a mixed list. */}
						{!state && (
							<td className="cell-meta">{a.owned ? "owned" : a.state}</td>
						)}
					</tr>
				))}
			</tbody>
		</table>
	);

	return (
		<>
			<PageHeader title={title} count={count} filter={<FilterBox />}>
				{sortControl}
			</PageHeader>
			{body}
		</>
	);
}

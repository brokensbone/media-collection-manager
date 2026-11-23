import "./pages-worklists.css";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { fetchJson } from "./api";
import { Cover } from "./Cover";
import { matchesQuery } from "./filter";
import { useHashParam } from "./hashState";
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
	Segmented,
	useAnnounceCount,
} from "./ui";

type Item = {
	id: number;
	artist: string;
	title: string;
	reason: string;
	has_art: boolean;
	spotify_id: string | null;
	album_type: string | null;
	release_year: number | null;
};
type Action = "keep" | "drop" | "snooze";
type Scope = "year" | "all";

export function Decide({
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
	const [scopeParam, setScopeParam] = useHashParam("scope");
	const full = limit == null;
	// Overview has no scope control and its count covers every album, so it shows all of them.
	const scope: Scope = !full || scopeParam === "all" ? "all" : "year";
	const year = new Date().getFullYear();

	const load = useCallback(() => {
		setFailed(false);
		fetchJson<Item[]>("/decide").then(setItems, () => setFailed(true));
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

	const all = items ?? [];
	const thisYear = all.filter((it) => it.release_year === year);
	const scoped = scope === "all" ? all : thisYear;
	const shown = scoped
		.filter((it) => matchesQuery(`${it.artist} ${it.title}`, query))
		.slice(0, limit);

	const { setSel, rowProps } = useRowKeys({
		count: shown.length,
		enabled: full,
		actions: {
			y: (i) => act(shown[i].id, "keep"),
			x: (i) => act(shown[i].id, "drop"),
			s: (i) => act(shown[i].id, "snooze"),
		},
	});
	useAnnounceCount(
		shown.length,
		scoped.length,
		full && items != null && query !== "",
	);

	const changeScope = (next: Scope) => {
		setScopeParam(next === "all" ? "all" : null);
		setSel(0);
	};

	let body: ReactNode;
	if (!items)
		body = failed ? (
			<ErrorState what="albums to judge" onRetry={load} />
		) : (
			<Loading rows={full ? 6 : 3} />
		);
	else if (items.length === 0)
		body = full ? (
			<EmptyState title="Nothing to judge." />
		) : (
			<p className="state-inline">Nothing waiting.</p>
		);
	else if (shown.length === 0 && query)
		body = full ? (
			<NoMatches
				query={query}
				what={scope === "year" ? "this year’s albums" : "Decide"}
			/>
		) : (
			<p className="state-inline">No matches for “{query}”.</p>
		);
	else if (shown.length === 0)
		body = (
			<EmptyState
				title="No albums match this view."
				hint="Albums with unknown release years are in All albums; Spotify release years fill in as saved albums sync."
				action={
					<button type="button" onClick={() => changeScope("all")}>
						Show all albums
					</button>
				}
			/>
		);
	else
		body = (
			<>
				<table className={full ? "rows worklist sticky-head" : "rows worklist"}>
					<colgroup>
						<col className="c-cover" />
						<col className="c-artist" />
						<col />
						<col className="c-meta" />
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
								<th scope="col">Why</th>
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
									{it.release_year != null && (
										<Badge>{String(it.release_year)}</Badge>
									)}
									{it.album_type && <Badge>{it.album_type}</Badge>}
								</td>
								<td className="cell-meta">{it.reason}</td>
								<td className="cell-actions">
									<div className="row-actions">
										<button
											type="button"
											className="btn-primary"
											onClick={() => act(it.id, "keep")}
										>
											Keep
											{full && <Kbd>y</Kbd>}
										</button>
										<button
											type="button"
											className="btn-quiet"
											onClick={() => act(it.id, "drop")}
										>
											Drop
											{full && <Kbd>x</Kbd>}
										</button>
										<button
											type="button"
											className="btn-quiet"
											onClick={() => act(it.id, "snooze")}
										>
											Snooze
											{full && <Kbd>s</Kbd>}
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
							["y", "keep"],
							["x", "drop"],
							["s", "snooze"],
						]}
					/>
				)}
			</>
		);

	if (!full) return body;
	return (
		<>
			<PageHeader
				title="Decide"
				count={
					items == null
						? undefined
						: shown.length === items.length
							? items.length
							: `${shown.length} of ${items.length}`
				}
				filter={<FilterBox />}
			>
				{items != null && items.length > 0 && (
					<Segmented<Scope>
						ariaLabel="Filter albums by release year"
						value={scope}
						onChange={changeScope}
						options={[
							{ value: "year", label: "This year", count: thisYear.length },
							{ value: "all", label: "All albums", count: items.length },
						]}
					/>
				)}
			</PageHeader>
			{body}
		</>
	);
}

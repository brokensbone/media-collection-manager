import "./pages-worklists.css";
import {
	type ReactNode,
	useCallback,
	useEffect,
	useRef,
	useState,
} from "react";
import { fetchJson } from "./api";
import { Cover } from "./Cover";
import { matchesQuery } from "./filter";
import { ExternalIcon } from "./icons";
import { useRowKeys } from "./keys";
import { Modal } from "./Modal";
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
	PollWarning,
	StatusBadge,
	type Tone,
	useAnnounceCount,
} from "./ui";

type Item = {
	id: number;
	artist: string;
	title: string;
	has_art: boolean;
	bandcamp_url: string;
	possibly_owned: boolean;
	owned_hint: string | null;
	spotify_id: string | null;
	album_type: string | null;
	pending_imports: {
		id: number;
		name: string;
		matched_album_id: number;
		state: "detected" | "queued" | "importing" | "failed";
	}[];
};

type Candidate = {
	beets_id: string;
	artist: string;
	title: string;
	has_release_group: boolean;
};

// A tracker torrent-search URL for the album. Artist and title go in tab-separated — the
// trackers' own copy links put a tab between them — which URLSearchParams encodes as %09
// (spaces as +). `extra` carries any fixed query params a tracker's basic search needs.
function trackerSearch(
	base: string,
	artist: string,
	title: string,
	extra: Record<string, string> = {},
): string {
	return `${base}?${new URLSearchParams({ searchstr: `${artist}\t${title}`, ...extra })}`;
}

// Orpheus's basic search needs these fixed params alongside searchstr.
const ORPHEUS_PARAMS = {
	tags_type: "1",
	order: "time",
	sort: "desc",
	group_results: "1",
	action: "basic",
	searchsubmit: "1",
};

const PENDING: Record<
	Item["pending_imports"][number]["state"],
	{ label: string; tone: Tone; pulse?: boolean }
> = {
	detected: { label: "Waiting in Import", tone: "info" },
	queued: { label: "Import queued", tone: "info" },
	importing: { label: "Importing", tone: "info", pulse: true },
	failed: { label: "Import failed", tone: "danger" },
};

function FindLink({
	href,
	children,
	hint,
}: {
	href: string;
	children: string;
	hint?: ReactNode;
}) {
	return (
		<a className="btn" href={href} target="_blank" rel="noreferrer">
			{children}
			<ExternalIcon size={12} />
			{hint}
		</a>
	);
}

export function Acquire({
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
	const [pollFailed, setPollFailed] = useState(false);
	const loaded = useRef(false);
	const [owning, setOwning] = useState<Item | null>(null); // the album being marked owned
	const [q, setQ] = useState("");
	const [results, setResults] = useState<Candidate[] | null>(null);
	const full = limit == null;

	// A failed poll after the first load keeps the last list on screen and only warns.
	const load = useCallback(() => {
		fetchJson<Item[]>("/acquire").then(
			(list) => {
				loaded.current = true;
				setItems(list);
				setFailed(false);
				setPollFailed(false);
			},
			() => (loaded.current ? setPollFailed(true) : setFailed(true)),
		);
	}, []);

	useEffect(() => {
		load();
		const timer = setInterval(load, 4000);
		return () => clearInterval(timer);
	}, [load]);

	// Search the library while the Mark-owned modal is open.
	useEffect(() => {
		if (!owning) return;
		let cancelled = false;
		fetchJson<Candidate[]>(`/library/search?q=${encodeURIComponent(q)}`)
			.then((r) => !cancelled && setResults(r))
			.catch(() => !cancelled && setResults([]));
		return () => {
			cancelled = true;
		};
	}, [owning, q]);

	const remove = useCallback((id: number) => {
		setItems((list) => (list ? list.filter((it) => it.id !== id) : list));
	}, []);

	const openOwn = useCallback((it: Item) => {
		setOwning(it);
		setQ(`${it.artist} ${it.title}`);
		setResults(null);
	}, []);

	const markOwned = useCallback(
		(id: number, beetsId?: string) => {
			fetch(`/albums/${id}/mark-owned`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ beets_id: beetsId ?? null }),
			}).then(() => onChange?.());
			remove(id);
			setOwning(null);
		},
		[remove, onChange],
	);

	const returnToSaved = useCallback(
		(id: number) => {
			fetch(`/albums/${id}/return-to-saved`, { method: "POST" }).then(() =>
				onChange?.(),
			);
			remove(id);
			setOwning(null);
		},
		[remove, onChange],
	);

	const shown = (items ?? [])
		.filter((it) => matchesQuery(`${it.artist} ${it.title}`, query))
		.slice(0, limit);
	useAnnounceCount(
		shown.length,
		items?.length ?? 0,
		full && items != null && query !== "",
	);
	const { rowProps } = useRowKeys({
		count: shown.length,
		enabled: full && !owning,
		actions: {
			b: (i) => window.open(shown[i].bandcamp_url, "_blank", "noreferrer"),
			m: (i) => openOwn(shown[i]),
		},
	});

	let body: ReactNode;
	if (!items)
		body = failed ? (
			<ErrorState
				what="the acquire list"
				onRetry={() => {
					setFailed(false);
					load();
				}}
			/>
		) : (
			<Loading rows={full ? 6 : 3} />
		);
	else if (items.length === 0)
		body = full ? (
			<EmptyState title="Nothing to acquire." />
		) : (
			<p className="state-inline">Nothing waiting.</p>
		);
	else if (shown.length === 0)
		body = full ? (
			<NoMatches query={query} what="Acquire" />
		) : (
			<p className="state-inline">No matches for “{query}”.</p>
		);
	else
		body = (
			<>
				<table
					className={`rows worklist acquire-table${full ? " sticky-head" : ""}`}
				>
					<colgroup>
						<col className="c-cover" />
						<col className="c-artist" />
						<col />
						<col className="c-find" />
						<col className="c-acquire-actions" />
					</colgroup>
					{full && (
						<thead>
							<tr>
								<th scope="col">
									<span className="sr-only">Cover</span>
								</th>
								<th scope="col">Artist</th>
								<th scope="col">Title</th>
								<th scope="col">Find</th>
								<th scope="col">
									<span className="sr-only">Actions</span>
								</th>
							</tr>
						</thead>
					)}
					<tbody>
						{shown.map((it, i) => (
							<tr key={it.id} {...rowProps(i)}>
								<Cover
									id={it.id}
									hasArt={it.has_art}
									spotifyId={it.spotify_id}
								/>
								<td className="cell-primary">{it.artist}</td>
								<td className="cell-secondary">
									{it.title}
									{it.album_type && <Badge>{it.album_type}</Badge>}
									{it.possibly_owned && (
										<span className="row-meta">
											<StatusBadge tone="warn">possibly owned</StatusBadge>
											<span className="sr-only">:</span> {it.owned_hint}
										</span>
									)}
									{it.pending_imports?.map((pending) => {
										const p = PENDING[pending.state];
										return (
											<span key={pending.id} className="row-meta">
												<a
													className="pending"
													href={`#${pending.state === "detected" ? "import" : "tasks"}?item=${pending.id}`}
												>
													<StatusBadge tone={p.tone} pulse={p.pulse}>
														{p.label}
													</StatusBadge>
													<span className="sr-only">:</span> {pending.name}
												</a>
											</span>
										);
									})}
								</td>
								<td className="cell-meta">
									<div className="find-links">
										<FindLink
											href={it.bandcamp_url}
											hint={full && <Kbd>b</Kbd>}
										>
											Bandcamp
										</FindLink>
										<FindLink
											href={trackerSearch(
												"https://redacted.sh/torrents.php",
												it.artist,
												it.title,
											)}
										>
											Red
										</FindLink>
										<FindLink
											href={trackerSearch(
												"https://orpheus.network/torrents.php",
												it.artist,
												it.title,
												ORPHEUS_PARAMS,
											)}
										>
											Ops
										</FindLink>
									</div>
								</td>
								<td className="cell-actions">
									<div className="row-actions">
										<button type="button" onClick={() => openOwn(it)}>
											Mark owned…
											{full && <Kbd>m</Kbd>}
										</button>
										<button
											type="button"
											className="btn-quiet"
											onClick={() => returnToSaved(it.id)}
										>
											Back to saved
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
							["b", "open Bandcamp"],
							["m", "mark owned…"],
						]}
					/>
				)}
			</>
		);

	return (
		<>
			{full && (
				<PageHeader
					title="Acquire"
					count={
						items == null
							? undefined
							: query
								? `${shown.length} of ${items.length}`
								: items.length
					}
					filter={<FilterBox />}
				/>
			)}
			{full && <PollWarning show={pollFailed} />}
			{body}

			{owning && (
				<Modal
					title={`Mark owned: ${owning.artist} — ${owning.title}`}
					onClose={() => setOwning(null)}
				>
					<input
						type="search"
						className="modal-search"
						aria-label="Search your library"
						data-autofocus
						value={q}
						onChange={(e) => setQ(e.target.value)}
						placeholder="Search your library…"
					/>
					<div className="candidates">
						{results === null ? (
							<p className="candidates-note">Searching…</p>
						) : results.length === 0 ? (
							<p className="candidates-note">
								No library matches — try a different search.
							</p>
						) : (
							results.map((c) => (
								<button
									key={c.beets_id}
									type="button"
									className="candidate"
									onClick={() => markOwned(owning.id, c.beets_id)}
								>
									<span>
										{c.artist} — {c.title}
									</span>
									{!c.has_release_group && <Badge>no MB id</Badge>}
								</button>
							))
						)}
					</div>
					<div className="modal-actions">
						<button type="button" onClick={() => markOwned(owning.id)}>
							Mark owned without a link
						</button>
					</div>
				</Modal>
			)}
		</>
	);
}

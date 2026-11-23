import "./pages-imports.css";
import {
	type ReactNode,
	useCallback,
	useEffect,
	useRef,
	useState,
} from "react";
import { fetchJson } from "./api";
import { matchesQuery } from "./filter";
import { useHashParam } from "./hashState";
import { dayLabel, type ImportItem } from "./importItem";
import { ImportReclassify } from "./importReclassify";
import {
	EmptyState,
	ErrorState,
	FilterBox,
	GroupHead,
	Loading,
	NoMatches,
	PageHeader,
	PollWarning,
	Segmented,
	StatusBadge,
	useAnnounceCount,
} from "./ui";

// The type a row belongs to for the filter bar. Keyed off import_target so the buckets are
// mutually exclusive and match where the file actually goes: a mixed-season TV pack routed to
// review shows under Review (needs attention), not TV — so each list is a clean batch to work.
type ItemType = "music" | "tv" | "film" | "workspace" | "review";
const TYPE_LABELS: [ItemType, string][] = [
	["music", "Music"],
	["tv", "TV"],
	["film", "Film"],
	["workspace", "Workspace"],
	["review", "Review"],
];

function itemType(it: ImportItem): ItemType {
	if (it.import_target === "review") return "review";
	if (it.import_target === "workspace") return "workspace";
	if (it.import_target === "tv") return "tv";
	if (it.import_target === "film") return "film";
	return "music"; // beets
}

export function Imports({
	onChange,
	query = "",
	limit,
}: {
	onChange?: () => void;
	query?: string;
	limit?: number;
}) {
	const [items, setItems] = useState<ImportItem[] | null>(null);
	const [failed, setFailed] = useState(false);
	const [scanning, setScanning] = useState(false);
	const [kindParam, setKindParam] = useHashParam("kind");
	const [itemParam] = useHashParam("item");
	const typeFilter: "all" | ItemType =
		limit == null && TYPE_LABELS.some(([k]) => k === kindParam)
			? (kindParam as ItemType)
			: "all";
	const linkedId = Number(itemParam);
	const focused = useRef(false);

	// Import/Discard both remove the row from this decision list (it becomes a Task, or is
	// dismissed). Hold the removed ids so an in-flight poll can't flash a row back before the
	// server catches up; drop the id once the server stops returning it.
	const removed = useRef<Set<number>>(new Set());

	const merge = useCallback(
		(prev: ImportItem[] | null, data: ImportItem[]): ImportItem[] => {
			const ids = new Set(data.map((it) => it.id));
			for (const id of [...removed.current])
				if (!ids.has(id)) removed.current.delete(id);
			const effective = data.filter((it) => !removed.current.has(it.id));
			if (!prev) return effective;
			// Preserve display order so a poll never reshuffles rows under the cursor; append new ones.
			const byId = new Map(effective.map((it) => [it.id, it]));
			const seen = new Set<number>();
			const kept: ImportItem[] = [];
			for (const row of prev) {
				const updated = byId.get(row.id);
				if (updated) {
					kept.push(updated);
					seen.add(row.id);
				}
			}
			return [...kept, ...effective.filter((it) => !seen.has(it.id))];
		},
		[],
	);

	const refresh = useCallback(() => {
		fetchJson<ImportItem[]>("/imports")
			.then((data) => {
				setItems((prev) => merge(prev, data));
				setFailed(false);
			})
			.catch(() => setFailed(true));
	}, [merge]);

	useEffect(() => {
		refresh();
		const t = setInterval(refresh, 4000);
		return () => clearInterval(t);
	}, [refresh]);

	useEffect(() => {
		if (
			!linkedId ||
			!items?.some((it) => it.id === linkedId) ||
			focused.current
		)
			return;
		focused.current = true;
		document
			.getElementById(`import-${linkedId}`)
			?.scrollIntoView?.({ block: "center" });
	}, [items, linkedId]);

	const act = useCallback(
		(id: number, method: "POST" | "DELETE") => {
			removed.current.add(id); // sticky removal until the server stops listing it as pending
			setItems((list) => list?.filter((it) => it.id !== id) ?? list);
			const url =
				method === "POST" ? `/imports/${id}/import` : `/imports/${id}`;
			fetch(url, { method }).then(() => {
				onChange?.();
				refresh();
			});
		},
		[onChange, refresh],
	);

	const scan = useCallback(() => {
		setScanning(true);
		fetch("/imports/scan", { method: "POST" })
			.then(refresh)
			.then(() => onChange?.())
			.finally(() => setScanning(false));
	}, [onChange, refresh]);

	const queryFiltered = (items ?? []).filter((it) =>
		matchesQuery(`${it.name} ${it.matched ?? ""}`, query),
	);
	const shown =
		typeFilter === "all"
			? queryFiltered
			: queryFiltered.filter((it) => itemType(it) === typeFilter);
	useAnnounceCount(
		shown.length,
		items?.length ?? 0,
		limit == null && items != null && (query !== "" || typeFilter !== "all"),
	);

	if (limit != null) {
		if (!items)
			return failed ? (
				<ErrorState what="imports" onRetry={refresh} />
			) : (
				<Loading rows={2} />
			);
		const top = newestFirst(shown).slice(0, limit);
		if (top.length === 0)
			return (
				<p className="state-inline">
					{items.length === 0
						? "Nothing waiting."
						: `No matches for “${query}”.`}
				</p>
			);
		return (
			<ImportTable
				rows={top}
				linkedId={linkedId}
				act={act}
				refresh={refresh}
				head={false}
			/>
		);
	}

	const counts: Record<ItemType, number> = {
		music: 0,
		tv: 0,
		film: 0,
		workspace: 0,
		review: 0,
	};
	for (const it of queryFiltered) counts[itemType(it)]++;
	const present = TYPE_LABELS.filter(([k]) => counts[k] > 0);
	const barTypes = TYPE_LABELS.filter(
		([k]) => counts[k] > 0 || typeFilter === k,
	);

	// Partition into discovery-day groups, newest first, so freshly-added drops are easy to find
	// instead of scattering alphabetically. created_at is immutable, so this order never reshuffles.
	const groups: { key: string; label: string; rows: ImportItem[] }[] = [];
	for (const it of newestFirst(shown)) {
		const key = it.created_at
			? new Date(it.created_at).toDateString()
			: "unknown";
		const g = groups.find((x) => x.key === key);
		if (g) g.rows.push(it);
		else groups.push({ key, label: dayLabel(it.created_at), rows: [it] });
	}

	const typeLabel = TYPE_LABELS.find(([k]) => k === typeFilter)?.[1];
	let content: ReactNode;
	if (!items)
		content = failed ? (
			<ErrorState what="imports" onRetry={refresh} />
		) : (
			<Loading rows={4} />
		);
	else if (items.length === 0)
		content = <EmptyState title="Nothing waiting to import." />;
	else if (queryFiltered.length === 0)
		content = <NoMatches query={query} what="Import" />;
	else if (shown.length === 0)
		content = (
			<EmptyState
				title={`No ${typeLabel} items waiting.`}
				action={
					<button type="button" onClick={() => setKindParam(null)}>
						Show all
					</button>
				}
			/>
		);
	else
		content = groups.map((g, i) => (
			<section key={g.key} className="import-day">
				<GroupHead title={g.label} count={g.rows.length} />
				<ImportTable
					rows={g.rows}
					linkedId={linkedId}
					act={act}
					refresh={refresh}
					head={i === 0}
				/>
			</section>
		));

	return (
		<>
			<PageHeader
				title="Import"
				count={
					items
						? shown.length === items.length
							? items.length
							: `${shown.length} of ${items.length}`
						: undefined
				}
				filter={<FilterBox placeholder="Filter name or match" />}
			>
				{(present.length > 1 || typeFilter !== "all") && (
					<Segmented
						ariaLabel="Kind"
						value={typeFilter}
						onChange={(v) => setKindParam(v === "all" ? null : v)}
						options={[
							{ value: "all", label: "All", count: queryFiltered.length },
							...barTypes.map(([k, label]) => ({
								value: k,
								label,
								count: counts[k],
							})),
						]}
					/>
				)}
				<button type="button" onClick={scan} disabled={scanning}>
					{scanning ? "Scanning…" : "Scan watch folder"}
				</button>
			</PageHeader>
			<PollWarning show={failed && items != null} />
			{content}
		</>
	);
}

function newestFirst(list: ImportItem[]): ImportItem[] {
	return [...list].sort((a, b) =>
		(b.created_at ?? "").localeCompare(a.created_at ?? ""),
	);
}

function ImportTable({
	rows,
	linkedId,
	act,
	refresh,
	head,
}: {
	rows: ImportItem[];
	linkedId: number;
	act: (id: number, method: "POST" | "DELETE") => void;
	refresh: () => void;
	head: boolean;
}) {
	return (
		<table className="rows tall no-cover import-table">
			<colgroup>
				<col />
				<col className="c-matched" />
				<col className="c-import-actions" />
			</colgroup>
			{/* Day groups each get a table; only the first shows its header, the rest keep it for screen readers. */}
			<thead className={head ? undefined : "sr-thead"}>
				<tr>
					<th scope="col">Name</th>
					<th scope="col">Matched</th>
					<th scope="col">Type</th>
				</tr>
			</thead>
			<tbody>
				{rows.map((it) => (
					<tr
						key={it.id}
						id={`import-${it.id}`}
						className={it.id === linkedId ? "linked" : undefined}
					>
						<td className="cell-primary">
							{it.name}
							<span className="row-meta">
								<span className="src">{it.source}</span>
								{it.classification_detail && <> · {it.classification_detail}</>}
								{it.destination_path && (
									<>
										{" · "}
										<span className="mono path">{it.destination_path}</span>
									</>
								)}
							</span>
						</td>
						<td className="cell-secondary">
							{it.matched ?? <span className="muted">no match</span>}
							{it.matched_owned && <StatusBadge tone="ok">owned</StatusBadge>}
							{it.missing && (
								<div className="missing-line">
									<StatusBadge tone="danger">
										file no longer in watch folder
									</StatusBadge>
								</div>
							)}
						</td>
						<td className="cell-actions">
							<div className="row-actions">
								<ImportReclassify
									item={it}
									onChange={refresh}
									disabled={it.missing}
								/>
								<span className="import-slot">
									{!it.missing &&
										(it.import_target === "review" ? (
											<StatusBadge tone="warn">needs review</StatusBadge>
										) : (
											<button
												type="button"
												className="btn-primary"
												onClick={() => act(it.id, "POST")}
											>
												Import
											</button>
										))}
								</span>
								<button
									type="button"
									className="btn-quiet"
									onClick={() => act(it.id, "DELETE")}
								>
									Discard
								</button>
							</div>
						</td>
					</tr>
				))}
			</tbody>
		</table>
	);
}

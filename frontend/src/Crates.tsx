import "./pages-library.css";
import {
	type MouseEvent,
	type ReactNode,
	useCallback,
	useEffect,
	useRef,
	useState,
} from "react";
import { fetchJson } from "./api";
import { matchesQuery } from "./filter";
import { setHashParams, useHashParam, useQuery } from "./hashState";
import { useRowKeys } from "./keys";
import {
	EmptyState,
	ErrorState,
	FilterBox,
	ListHints,
	Loading,
	NoMatches,
	PageHeader,
	useAnnounceCount,
	usePageTitle,
} from "./ui";

// A crate view: the box the operator is looking at, its ancestors, its sub-boxes, and the
// records loose directly here. Mirrors the backend's BoxView (crates §2).
type Crumb = { id: number; name: string };
type ChildBox = {
	id: number;
	name: string;
	loose_count: number;
	total_count: number;
};
type BoxRecord = {
	beets_id: string;
	artist: string;
	title: string;
	year: number | null;
	media: string | null;
};
type BoxView = {
	id: number;
	name: string;
	parent_id: number | null;
	breadcrumb: Crumb[];
	children: ChildBox[];
	records: BoxRecord[];
	loose_count: number;
	total_count: number;
	soft_cap: number;
	over_cap: boolean;
};

// A proposed way to divide this box's loose records into sub-boxes (crates §4). Mirrors the
// backend's SplitCandidate: one axis, the groups it would create, and how many records it leaves
// loose.
type SplitGroup = { name: string; count: number };
type SplitCandidate = {
	key: string;
	label: string;
	groups: SplitGroup[];
	covers: number;
	leaves: number;
};

// The box being viewed lives in the URL (#crates?box=<id>) so descending, breadcrumbs and the
// browser back button all work. No box param = the root Collection.
function boxHref(id: number | null): string {
	return id == null ? "#crates" : `#crates?box=${id}`;
}

function gotoBox(id: number | null) {
	setHashParams({ box: id, q: null });
}

export function Crates() {
	const [boxParam] = useHashParam("box");
	const boxId = boxParam ? Number(boxParam) : null;
	const query = useQuery();
	const [view, setView] = useState<BoxView | null>(null);
	const [failed, setFailed] = useState(false);
	const [selected, setSelected] = useState<Set<string>>(new Set());
	const [error, setError] = useState<string | null>(null);
	const [newSub, setNewSub] = useState("");
	const [newTarget, setNewTarget] = useState("");
	// null = the split panel is closed; an array (possibly empty) = suggestions have been fetched.
	const [splits, setSplits] = useState<SplitCandidate[] | null>(null);
	const selectAll = useRef<HTMLInputElement>(null);
	// The last record toggled, by beets id: a shift-click selects everything between it and the next.
	const anchor = useRef<string | null>(null);

	const load = useCallback(() => {
		setFailed(false);
		const url = boxId == null ? "/crates/box" : `/crates/box/${boxId}`;
		fetchJson<BoxView>(url).then(
			(v) => {
				setView(v);
				setSelected(new Set());
				setSplits(null); // stale after any reload — the loose set it was computed from has changed
			},
			() => {
				setView(null);
				setFailed(true);
			},
		);
	}, [boxId]);

	useEffect(load, [load]);

	usePageTitle(view && view.parent_id != null ? `${view.name} · Crates` : null);

	const records = view?.records ?? [];
	const shown = records.filter((r) =>
		matchesQuery(`${r.artist} ${r.title}`, query),
	);
	// Actions only touch selected records the filter still shows, so nothing hidden moves.
	const ids = shown
		.filter((r) => selected.has(r.beets_id))
		.map((r) => r.beets_id);
	const allSelected = shown.length > 0 && ids.length === shown.length;

	useAnnounceCount(shown.length, records.length, view != null && !!query);

	const toggleAt = (i: number, range = false) => {
		const target = shown[i];
		if (!target) return;
		const on = !selected.has(target.beets_id);
		const from = range
			? shown.findIndex((r) => r.beets_id === anchor.current)
			: -1;
		const span =
			from === -1
				? [target]
				: shown.slice(Math.min(from, i), Math.max(from, i) + 1);
		anchor.current = target.beets_id;
		setSelected((prev) => {
			const next = new Set(prev);
			for (const r of span)
				if (on) next.add(r.beets_id);
				else next.delete(r.beets_id);
			return next;
		});
	};

	const { rowProps } = useRowKeys({
		count: shown.length,
		actions: {
			" ": (i) => {
				// Leave space to a focused control (checkbox, button) so it doesn't toggle twice.
				if (
					(document.activeElement as HTMLElement | null)?.closest?.(
						"button, a, input, select",
					)
				)
					return false;
				toggleAt(i);
			},
		},
	});

	useEffect(() => {
		if (selectAll.current)
			selectAll.current.indeterminate = ids.length > 0 && !allSelected;
	});

	// Post a mutation, surface any rejection (e.g. a blocked delete), then reload the view.
	const act = useCallback(
		async (url: string, init: RequestInit): Promise<boolean> => {
			setError(null);
			const r = await fetch(url, {
				...init,
				headers: {
					"content-type": "application/json",
					...(init.headers ?? {}),
				},
			});
			if (!r.ok) {
				const body = await r.json().catch(() => null);
				setError(body?.detail ?? "That didn’t work.");
				return false;
			}
			return true;
		},
		[],
	);

	if (!view)
		return (
			<>
				<PageHeader title="Crates" filter={<FilterBox />} />
				{failed ? (
					<ErrorState what="this crate" onRetry={load} />
				) : (
					<Loading rows={8} compact />
				)}
			</>
		);

	const toggleAll = () => {
		setSelected((prev) => {
			const next = new Set(prev);
			for (const r of shown)
				if (allSelected) next.delete(r.beets_id);
				else next.add(r.beets_id);
			return next;
		});
	};

	// The checkbox is the keyboard path; a click anywhere else on the row is a shortcut to it.
	const onRowClick = (e: MouseEvent, i: number) => {
		if ((e.target as HTMLElement).closest("input, a, button, label")) return;
		toggleAt(i, e.shiftKey);
	};

	const createSub = async () => {
		if (!newSub.trim()) return;
		if (
			await act("/crates/box", {
				method: "POST",
				body: JSON.stringify({ name: newSub.trim(), parent_id: view.id }),
			})
		) {
			setNewSub("");
			load();
		}
	};

	const rename = async () => {
		const name = window.prompt("Rename box", view.name)?.trim();
		if (
			name &&
			(await act(`/crates/box/${view.id}`, {
				method: "PATCH",
				body: JSON.stringify({ name }),
			}))
		)
			load();
	};

	const remove = async () => {
		if (await act(`/crates/box/${view.id}`, { method: "DELETE" }))
			gotoBox(view.parent_id);
	};

	const kickUp = async () => {
		if (
			await act(`/crates/box/${view.id}/kick-up`, {
				method: "POST",
				body: JSON.stringify({ beets_ids: ids }),
			})
		)
			load();
	};

	const fileInto = async (childId: number) => {
		if (
			await act(`/crates/box/${view.id}/file`, {
				method: "POST",
				body: JSON.stringify({ beets_ids: ids, child_box_id: childId }),
			})
		)
			load();
	};

	const fileNew = async () => {
		if (!newTarget.trim()) return;
		if (
			await act(`/crates/box/${view.id}/file`, {
				method: "POST",
				body: JSON.stringify({
					beets_ids: ids,
					new_box_name: newTarget.trim(),
				}),
			})
		) {
			setNewTarget("");
			load();
		}
	};

	const suggestSplit = async () => {
		setError(null);
		const r = await fetch(`/crates/box/${view.id}/split-suggestions`);
		setSplits(r.ok ? await r.json() : []);
	};

	const applySplit = async (facet: string) => {
		if (
			await act(`/crates/box/${view.id}/split`, {
				method: "POST",
				body: JSON.stringify({ facet }),
			})
		)
			load(); // reload shows the new sub-boxes and clears the (now stale) suggestions panel
	};

	const isRoot = view.parent_id == null;
	const capPct = Math.min(
		100,
		Math.round((view.loose_count / Math.max(1, view.soft_cap)) * 100),
	);

	let loose: ReactNode;
	if (records.length === 0) loose = <EmptyState title="Nothing loose here." />;
	else if (shown.length === 0)
		loose = <NoMatches query={query} what="this crate’s loose records" />;
	else
		loose = (
			<table className="rows compact crate-table sticky-head">
				<colgroup>
					<col className="c-check" />
					<col className="c-artist" />
					<col />
					<col className="c-meta" />
				</colgroup>
				<thead>
					<tr>
						<th scope="col">
							<input
								ref={selectAll}
								type="checkbox"
								aria-label="Select all loose records"
								checked={allSelected}
								onChange={toggleAll}
							/>
						</th>
						<th scope="col">Artist</th>
						<th scope="col">Title</th>
						<th scope="col">Year · media</th>
					</tr>
				</thead>
				<tbody>
					{shown.map((r, i) => {
						const on = selected.has(r.beets_id);
						return (
							<tr
								key={r.beets_id}
								{...rowProps(i, on ? "checked" : undefined)}
								aria-selected={on || undefined}
								onClick={(e) => onRowClick(e, i)}
							>
								<td className="cell-check">
									<input
										type="checkbox"
										aria-label={`Select ${r.artist} — ${r.title}`}
										checked={on}
										readOnly
										onClick={(e) => toggleAt(i, e.shiftKey)}
									/>
								</td>
								<td className="cell-primary">{r.artist}</td>
								<td className="cell-secondary">{r.title}</td>
								<td className="cell-meta">
									{[r.year, r.media].filter(Boolean).join(" · ")}
								</td>
							</tr>
						);
					})}
				</tbody>
			</table>
		);

	return (
		<section className={ids.length > 0 ? "crates has-selection" : "crates"}>
			<PageHeader
				title={isRoot ? "Crates" : view.name}
				count={view.total_count}
				filter={<FilterBox />}
				above={
					isRoot ? undefined : (
						<nav className="crumbs" aria-label="Breadcrumb">
							<ol>
								{view.breadcrumb.map((c) => (
									<li key={c.id}>
										{c.id === view.id ? (
											<span className="crumb-here" aria-current="page">
												{c.name}
											</span>
										) : (
											<a
												href={boxHref(
													c.id === view.breadcrumb[0].id ? null : c.id,
												)}
											>
												{c.id === view.breadcrumb[0].id ? "Crates" : c.name}
											</a>
										)}
									</li>
								))}
							</ol>
						</nav>
					)
				}
			>
				{!isRoot && (
					<>
						<button type="button" className="btn-quiet" onClick={rename}>
							Rename
						</button>
						<button type="button" className="btn-quiet" onClick={remove}>
							Delete
						</button>
					</>
				)}
			</PageHeader>

			<div className={`cap-meter${view.over_cap ? " over" : ""}`}>
				{/* biome-ignore lint/a11y/useSemanticElements: native <meter> styling differs per browser and cannot take the warn tone reliably */}
				<div
					className="cap-bar"
					role="meter"
					aria-label="Loose records"
					aria-valuemin={0}
					aria-valuemax={view.soft_cap}
					aria-valuenow={view.loose_count}
				>
					<div className="cap-fill" style={{ width: `${capPct}%` }} />
				</div>
				<span className="cap-label">
					{view.loose_count} loose / {view.soft_cap}
					{view.over_cap &&
						" — getting full, consider splitting into sub-boxes"}
				</span>
			</div>

			{error && (
				<p className="crate-error" role="alert">
					{error}
				</p>
			)}

			<h2 className="crate-section">Sub-boxes</h2>
			<div className="subbox-bar">
				{view.children.length > 0 && (
					<ul className="chips">
						{view.children.map((c) => (
							<li key={c.id}>
								<a className="chip-link" href={boxHref(c.id)}>
									<span className="chip-name">{c.name}</span>
									<span className="chip-count">{c.total_count}</span>
								</a>
							</li>
						))}
					</ul>
				)}
				<div className="subbox-add">
					<input
						type="text"
						aria-label="New sub-box name"
						placeholder="new sub-box…"
						value={newSub}
						onChange={(e) => setNewSub(e.target.value)}
						onKeyDown={(e) => e.key === "Enter" && createSub()}
					/>
					<button type="button" onClick={createSub}>
						Add
					</button>
				</div>
				<button type="button" className="suggest-split" onClick={suggestSplit}>
					Suggest a split
				</button>
			</div>

			{splits !== null &&
				(splits.length === 0 ? (
					<p className="state-inline">No clean split found — file by hand.</p>
				) : (
					<ul className="splits">
						{splits.map((s) => (
							<li key={s.key} className="split">
								<span className="split-desc">
									<strong>{s.label}</strong> —{" "}
									{s.groups.map((g) => `${g.name} (${g.count})`).join(" · ")} —
									leaves {s.leaves} loose
								</span>
								<button type="button" onClick={() => applySplit(s.key)}>
									Apply
								</button>
							</li>
						))}
					</ul>
				))}

			<h2 className="crate-section">
				Loose records{" "}
				<span className="crate-section-count">
					{query && records.length > 0
						? `${shown.length} of ${records.length}`
						: records.length}
				</span>
			</h2>

			{/* Always rendered so selecting a record never pushes the rows down. */}
			{shown.length > 0 && (
				<div className={ids.length > 0 ? "move-bar active" : "move-bar"}>
					{ids.length === 0 ? (
						<span className="move-hint">
							Select records to file them. Shift-click selects a range.
						</span>
					) : (
						<>
							<span className="move-count">{ids.length} selected</span>
							<button type="button" onClick={kickUp} disabled={isRoot}>
								Kick up
							</button>
							{view.children.length > 0 && (
								<label className="move-to">
									Move to{" "}
									<select
										value=""
										onChange={(e) =>
											e.target.value && fileInto(Number(e.target.value))
										}
									>
										<option value="">a sub-box…</option>
										{view.children.map((c) => (
											<option key={c.id} value={c.id}>
												{c.name}
											</option>
										))}
									</select>
								</label>
							)}
							<span className="move-new">
								<input
									type="text"
									aria-label="New box name"
									placeholder="or a new box…"
									value={newTarget}
									onChange={(e) => setNewTarget(e.target.value)}
									onKeyDown={(e) => e.key === "Enter" && fileNew()}
								/>
								<button type="button" onClick={fileNew}>
									Move
								</button>
							</span>
						</>
					)}
				</div>
			)}

			{loose}
			{shown.length > 0 && (
				<ListHints
					items={[
						["j/k", "move"],
						["space", "select"],
						["shift-click", "select a range"],
					]}
				/>
			)}
		</section>
	);
}

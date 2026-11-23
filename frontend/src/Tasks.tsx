import "./pages-imports.css";
import {
	Fragment,
	type ReactNode,
	useCallback,
	useEffect,
	useRef,
	useState,
} from "react";
import { fetchJson } from "./api";
import { useHashParam } from "./hashState";
import {
	type ImportItem,
	type ImportState,
	labelKind,
	whenLabel,
	whenTitle,
} from "./importItem";
import { ImportReclassify } from "./importReclassify";
import { shouldIgnoreKey, useRowKeys } from "./keys";
import {
	EmptyState,
	ErrorState,
	FilterBox,
	GroupHead,
	IMPORT_STATE_TONE,
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

const STATUS: Record<ImportState, string> = {
	detected: "",
	queued: "queued",
	importing: "importing…",
	imported: "imported ✓",
	skipped: "already in library",
	failed: "failed",
};

// Status groups shown top-to-bottom in the Tasks view. Completed (imported/skipped) is last and,
// in the default view, limited to the recent window server-side; the archive shows all of it.
const GROUPS: { label: string; states: ImportState[]; tone?: Tone }[] = [
	{ label: "In progress", states: ["importing"] },
	{ label: "Queued", states: ["queued"] },
	{ label: "Failed", states: ["failed"], tone: "danger" },
	{ label: "Completed", states: ["imported", "skipped"] },
];
const ACTIVE: ImportState[] = ["importing", "queued", "failed"];

export function Tasks({
	onChange,
	query = "",
	archive = false,
	limit,
}: {
	onChange?: () => void;
	query?: string;
	archive?: boolean;
	limit?: number;
}) {
	const [items, setItems] = useState<ImportItem[] | null>(null);
	const [failed, setFailed] = useState(false);
	// The expanded failure log is mirrored in the URL (#tasks?log=42) so a specific failure is
	// shareable/deep-linkable; the archive has no failed rows, so it never uses this.
	const [logParam, setLogParam] = useHashParam("log");
	const openLog = archive || !logParam ? null : Number(logParam);
	const [itemParam] = useHashParam("item");
	const linkedId = Number(itemParam);
	const removed = useRef<Set<number>>(new Set());
	const focused = useRef(false);

	const toggleLog = useCallback(
		(id: number) => setLogParam(openLog === id ? null : String(id)),
		[openLog, setLogParam],
	);

	useEffect(() => {
		if (openLog == null) return;
		function onKey(e: KeyboardEvent) {
			if (e.key !== "Escape" || shouldIgnoreKey(e)) return;
			setLogParam(null);
		}
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [openLog, setLogParam]);

	const refresh = useCallback(() => {
		fetchJson<ImportItem[]>(archive ? "/imports/archive" : "/imports/tasks")
			.then((data) => {
				setItems(data.filter((it) => !removed.current.has(it.id)));
				setFailed(false);
			})
			.catch(() => setFailed(true));
	}, [archive]);

	// Poll the live Tasks view so queued → importing → completed updates on screen; the archive is
	// historical, so fetch it once.
	useEffect(() => {
		refresh();
		if (archive) return;
		const t = setInterval(refresh, 4000);
		return () => clearInterval(t);
	}, [refresh, archive]);

	const act = useCallback(
		(id: number, method: "POST" | "DELETE") => {
			if (method === "DELETE") {
				removed.current.add(id);
				setItems((list) => list?.filter((it) => it.id !== id) ?? list);
			}
			const url =
				method === "POST" ? `/imports/${id}/import` : `/imports/${id}`;
			fetch(url, { method }).then(() => {
				onChange?.();
				refresh();
			});
		},
		[onChange, refresh],
	);

	// Bring a deep-linked failure into view once its row has rendered.
	const hasItems = items != null;
	useEffect(() => {
		if (openLog == null || !hasItems) return;
		document
			.getElementById(`task-${openLog}`)
			?.scrollIntoView?.({ block: "center" });
	}, [openLog, hasItems]);

	useEffect(() => {
		if (
			!linkedId ||
			!items?.some((it) => it.id === linkedId) ||
			focused.current
		)
			return;
		focused.current = true;
		document
			.getElementById(`task-${linkedId}`)
			?.scrollIntoView?.({ block: "center" });
	}, [items, linkedId]);

	const shown = (items ?? []).filter((it) =>
		`${it.name} ${it.matched ?? ""}`
			.toLowerCase()
			.includes(query.toLowerCase()),
	);
	useAnnounceCount(
		shown.length,
		items?.length ?? 0,
		limit == null && items != null && query !== "",
	);

	const grouped = archive
		? [{ label: "", states: [], rows: shown }]
		: GROUPS.map((g) => ({
				...g,
				rows: shown.filter((it) => g.states.includes(it.state)),
			})).filter((g) => g.rows.length > 0);
	const cursorRows = grouped.flatMap((g) => g.rows);
	const indexOf = new Map(cursorRows.map((it, i) => [it.id, i]));
	const full = limit == null;
	const { rowProps, setSel } = useRowKeys({
		count: full ? cursorRows.length : 0,
		enabled: full,
		actions: {
			r: (i) =>
				cursorRows[i]?.state === "failed" && act(cursorRows[i].id, "POST"),
			l: (i) =>
				cursorRows[i]?.state === "failed" &&
				cursorRows[i].error_detail &&
				toggleLog(cursorRows[i].id),
		},
	});
	const linkedIndex = cursorRows.findIndex((it) => it.id === linkedId);
	useEffect(() => {
		if (linkedIndex >= 0) setSel(linkedIndex);
	}, [linkedIndex, setSel]);

	const table = (list: ImportItem[], head = true) => (
		<TaskTable
			rows={list}
			head={head}
			linkedId={linkedId}
			openLog={openLog}
			toggleLog={toggleLog}
			act={act}
			refresh={refresh}
			rowProps={
				full
					? (it) =>
							rowProps(
								indexOf.get(it.id) ?? -1,
								it.id === linkedId ? "linked" : undefined,
							)
					: undefined
			}
		/>
	);

	const loadState = !items ? (
		failed ? (
			<ErrorState
				what={archive ? "the archive" : "import tasks"}
				onRetry={refresh}
			/>
		) : (
			<Loading rows={limit != null ? 2 : 4} />
		)
	) : null;

	if (limit != null) {
		if (loadState) return loadState;
		const active = shown
			.filter((it) => ACTIVE.includes(it.state))
			.sort((a, b) => ACTIVE.indexOf(a.state) - ACTIVE.indexOf(b.state))
			.slice(0, limit);
		if (active.length === 0)
			return (
				<p className="state-inline">
					{query && items?.length
						? `No matches for “${query}”.`
						: "Nothing waiting."}
				</p>
			);
		return table(active, false);
	}

	// Match the nav: the live view counts work still to do; completed rows count in their group.
	const isActive = (it: ImportItem) => archive || ACTIVE.includes(it.state);
	const total = items?.filter(isActive).length ?? 0;
	const shownTotal = shown.filter(isActive).length;
	const count = items
		? shownTotal === total
			? total
			: `${shownTotal} of ${total}`
		: undefined;
	const header = archive ? (
		<PageHeader
			title="Completed archive"
			count={count}
			back={{ href: "#tasks", label: "Back to tasks" }}
			filter={<FilterBox placeholder="Filter name or match" />}
		/>
	) : (
		<PageHeader
			title="Tasks"
			count={count}
			filter={<FilterBox placeholder="Filter name or match" />}
		>
			<a href="#archive" className="archive-link">
				View completed archive →
			</a>
		</PageHeader>
	);

	let content: ReactNode = loadState;
	if (!items) {
		// loading or error, set above
	} else if (items.length === 0)
		content = (
			<EmptyState
				title={archive ? "No completed imports." : "No import tasks."}
			/>
		);
	else if (shown.length === 0)
		content = (
			<NoMatches query={query} what={archive ? "the archive" : "Tasks"} />
		);
	else if (archive)
		content = (
			<>
				{table(shown)}
				<ListHints items={[["j/k", "move"]]} />
			</>
		);
	else
		content = (
			<>
				<TaskHead />
				{grouped.map((g) => (
					<section key={g.label} className="task-group">
						<GroupHead title={g.label} count={g.rows.length} tone={g.tone} />
						{table(g.rows, false)}
					</section>
				))}
				<ListHints
					items={[
						["j/k", "move"],
						["r", "retry"],
						["l", "log"],
						["Esc", "close log"],
					]}
				/>
			</>
		);

	return (
		<>
			{header}
			<PollWarning show={failed && items != null} />
			{content}
		</>
	);
}

const COLS = (
	<colgroup>
		<col />
		<col className="c-when" />
		<col className="c-task-actions" />
	</colgroup>
);

// Status groups each get their own table, so the visible column header sits once above them all.
function TaskHead() {
	return (
		<table
			className="rows tall no-cover tasks-table head-only"
			aria-hidden="true"
		>
			{COLS}
			<thead>
				<tr>
					<th>Name</th>
					<th>When</th>
					<th>Status</th>
				</tr>
			</thead>
		</table>
	);
}

type RowProps = ReturnType<ReturnType<typeof useRowKeys>["rowProps"]>;

function TaskTable({
	rows,
	head,
	linkedId,
	openLog,
	toggleLog,
	act,
	refresh,
	rowProps,
}: {
	rows: ImportItem[];
	head: boolean;
	rowProps?: (it: ImportItem) => RowProps;
	linkedId: number;
	openLog: number | null;
	toggleLog: (id: number) => void;
	act: (id: number, method: "POST" | "DELETE") => void;
	refresh: () => void;
}) {
	return (
		<table className="rows tall no-cover tasks-table">
			{COLS}
			<thead className={head ? undefined : "sr-thead"}>
				<tr>
					<th scope="col">Name</th>
					<th scope="col">When</th>
					<th scope="col">Status</th>
				</tr>
			</thead>
			<tbody>
				{rows.map((it) => (
					<Fragment key={it.id}>
						<tr
							id={`task-${it.id}`}
							{...(rowProps?.(it) ?? {
								className: it.id === linkedId ? "linked" : undefined,
							})}
						>
							<td className="cell-primary">
								{it.matched ?? it.name}
								<span className="row-meta">
									{it.matched && (
										<>
											<span className="raw-name">{it.name}</span>
											{" · "}
										</>
									)}
									<span className="src">{it.source}</span>
									{` · ${labelKind(it.media_kind)}`}
									{it.destination_path && (
										<>
											{" · "}
											<span className="mono path">{it.destination_path}</span>
										</>
									)}
								</span>
							</td>
							<td className="cell-meta nowrap" title={whenTitle(it.updated_at)}>
								{whenLabel(it.updated_at)}
							</td>
							<td className="cell-actions">
								<div className="row-actions task-actions">
									<span className="task-status">
										{STATUS[it.state] && (
											<StatusBadge
												tone={IMPORT_STATE_TONE[it.state]}
												pulse={it.state === "importing"}
											>
												{STATUS[it.state]}
											</StatusBadge>
										)}
									</span>
									{it.state !== "imported" &&
										it.state !== "skipped" &&
										it.state !== "importing" && (
											<ImportReclassify item={it} onChange={refresh} />
										)}
									{it.state === "failed" && (
										<>
											{it.error_detail && (
												<button
													type="button"
													className="btn-quiet"
													aria-expanded={openLog === it.id}
													onClick={() => toggleLog(it.id)}
												>
													{openLog === it.id ? "Hide log" : "Log"}
													{rowProps && <Kbd>l</Kbd>}
												</button>
											)}
											<button
												type="button"
												className="btn-primary"
												onClick={() => act(it.id, "POST")}
											>
												Retry
												{rowProps && <Kbd>r</Kbd>}
											</button>
											<button
												type="button"
												className="btn-quiet"
												onClick={() => act(it.id, "DELETE")}
											>
												Discard
											</button>
										</>
									)}
								</div>
							</td>
						</tr>
						{openLog === it.id && it.error_detail && (
							<tr className="log-row">
								<td colSpan={3}>
									<pre className="import-log">{it.error_detail}</pre>
								</td>
							</tr>
						)}
					</Fragment>
				))}
			</tbody>
		</table>
	);
}

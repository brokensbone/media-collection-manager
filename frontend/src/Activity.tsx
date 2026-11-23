import "./pages-tools.css";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { fetchJson } from "./api";
import { matchesQuery } from "./filter";
import { useHashParam, useQuery } from "./hashState";
import { formatDate } from "./Radio";
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

// Live tail of what the worker is doing, one row per item it processes (resolve, own, import,
// …). Polls /events?after=<cursor> every ~1.5s and appends; newest shown first, DOM capped.
type Event = {
	id: number;
	created_at: string;
	job: string;
	type: string;
	message: string;
	album_id: number | null;
};

const MAX_ROWS = 200;
const POLL_MS = 1500;
const ERROR_TYPES = new Set(["error", "failed"]);
const QUIET_TYPES = new Set(["no_match", "skipped", "duplicate"]);

const pad = (n: number) => String(n).padStart(2, "0");

function dayKey(d: Date): string {
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function dayTitle(d: Date): string {
	const today = new Date();
	const yesterday = new Date(
		today.getFullYear(),
		today.getMonth(),
		today.getDate() - 1,
	);
	if (dayKey(d) === dayKey(today)) return "Today";
	if (dayKey(d) === dayKey(yesterday)) return "Yesterday";
	return formatDate(d);
}

export function Activity() {
	const query = useQuery();
	const [show, setShow] = useHashParam("show");
	const errorsOnly = show === "errors";
	const [events, setEvents] = useState<Event[]>([]);
	const [loaded, setLoaded] = useState(false);
	const [failed, setFailed] = useState(false);
	const cursor = useRef<number | null>(null);
	const tickRef = useRef<() => void>(() => {});

	useEffect(() => {
		let stopped = false;
		async function tick() {
			const url =
				cursor.current == null ? "/events" : `/events?after=${cursor.current}`;
			try {
				const rows = await fetchJson<Event[]>(url);
				if (stopped) return;
				setLoaded(true);
				setFailed(false);
				if (rows.length) {
					cursor.current = rows[rows.length - 1].id;
					setEvents((prev) => [...prev, ...rows].slice(-MAX_ROWS));
				}
			} catch {
				// a poll blip is fine — the next tick retries from the same cursor
				if (!stopped) setFailed(true);
			}
		}
		tickRef.current = tick;
		tick();
		const handle = setInterval(tick, POLL_MS);
		return () => {
			stopped = true;
			clearInterval(handle);
		};
	}, []);

	const errorCount = events.filter((e) => ERROR_TYPES.has(e.type)).length;
	const shown = events
		.filter(
			(e) =>
				(!errorsOnly || ERROR_TYPES.has(e.type)) &&
				matchesQuery(`${e.job} ${e.message}`, query),
		)
		.reverse();
	useAnnounceCount(shown.length, events.length, !!query || errorsOnly);

	const groups: { key: string; title: string; rows: Event[] }[] = [];
	for (const e of shown) {
		const d = new Date(e.created_at);
		const key = dayKey(d);
		const last = groups[groups.length - 1];
		if (last?.key === key) last.rows.push(e);
		else groups.push({ key, title: dayTitle(d), rows: [e] });
	}

	let body: ReactNode;
	if (!loaded)
		body = failed ? (
			<ErrorState what="activity" onRetry={() => tickRef.current()} />
		) : (
			<Loading compact />
		);
	else if (events.length === 0)
		body = <EmptyState title="No worker activity yet." />;
	else if (shown.length === 0)
		body = query ? (
			<NoMatches query={query} what="activity" />
		) : (
			<EmptyState title="No errors in recent activity." />
		);
	else
		body = groups.map((g, i) => (
			<section key={g.key}>
				<GroupHead title={g.title} count={g.rows.length} />
				<table className="rows compact no-cover activity">
					<colgroup>
						<col className="c-time" />
						<col className="c-job" />
						<col />
					</colgroup>
					<thead className={i === 0 ? undefined : "sr-thead"}>
						<tr>
							<th scope="col">Time</th>
							<th scope="col">Job</th>
							<th scope="col">Message</th>
						</tr>
					</thead>
					<tbody>
						{g.rows.map((e) => (
							<EventRow key={e.id} event={e} />
						))}
					</tbody>
				</table>
			</section>
		));

	return (
		<>
			<PageHeader
				title="Activity"
				filter={<FilterBox placeholder="Filter message or job" />}
			>
				<Segmented
					ariaLabel="Show"
					value={errorsOnly ? "errors" : "all"}
					onChange={(v) =>
						setShow(v === "errors" ? "errors" : null, { replace: true })
					}
					options={[
						{ value: "all", label: "All" },
						{ value: "errors", label: "Errors", count: errorCount },
					]}
				/>
			</PageHeader>
			<PollWarning show={loaded && failed} />
			{body}
		</>
	);
}

function EventRow({ event: e }: { event: Event }) {
	const d = new Date(e.created_at);
	const isError = ERROR_TYPES.has(e.type);
	return (
		<tr className={`ev ev-${e.type}`}>
			<td className="ev-time">
				<time dateTime={e.created_at}>
					{pad(d.getHours())}:{pad(d.getMinutes())}:{pad(d.getSeconds())}
				</time>
			</td>
			<td className="ev-job-cell">
				<span className="ev-job">{e.job}</span>
			</td>
			<td className="ev-message">
				{isError && <StatusBadge tone="danger">error</StatusBadge>}
				<span className={QUIET_TYPES.has(e.type) ? "muted" : undefined}>
					{e.message}
				</span>
			</td>
		</tr>
	);
}

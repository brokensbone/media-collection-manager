import "./pages-tools.css";
import {
	type ReactNode,
	useCallback,
	useEffect,
	useRef,
	useState,
} from "react";
import { fetchJson } from "./api";
import {
	EmptyState,
	ErrorState,
	Loading,
	PageHeader,
	SegmentedLinks,
	usePageTitle,
} from "./ui";

type ScheduleSummary = {
	schedule_date: string;
	note: string | null;
	session_count: number;
	duration_seconds: number;
};

type ScheduleItem = {
	position: number;
	kind: "track" | "album";
	beets_id: string | null;
	item_id: string | null;
	artist: string | null;
	title: string;
	duration_seconds: number | null;
	tracks: ScheduleItem[] | null;
};

type ScheduleSession = {
	position: number;
	kind: "track_hour" | "album_session";
	title: string;
	starts_at: string | null;
	note: string | null;
	duration_seconds: number;
	items: ScheduleItem[];
};

type Schedule = ScheduleSummary & { sessions: ScheduleSession[] };

// Hand-written rather than toLocaleDateString, so output doesn't depend on the ICU build.
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
	"Jan",
	"Feb",
	"Mar",
	"Apr",
	"May",
	"Jun",
	"Jul",
	"Aug",
	"Sep",
	"Oct",
	"Nov",
	"Dec",
];

export function formatDate(d: Date, withYear = true): string {
	const s = `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
	return withYear ? `${s} ${d.getFullYear()}` : s;
}

function isoDay(iso: string): Date {
	const [y, m, d] = iso.split("-").map(Number);
	return new Date(y, m - 1, d);
}

function formatMonth(isoMonth: string): string {
	const [y, m] = isoMonth.split("-").map(Number);
	return `${MONTHS[m - 1]} ${y}`;
}

export function duration(seconds: number): string {
	const minutes = Math.round(seconds / 60);
	if (minutes < 60) return `${minutes}m`;
	return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

export function Radio({
	selectedDate,
	onSelectDate,
}: {
	selectedDate: string | null;
	onSelectDate?: (date: string) => void;
}) {
	const [schedules, setSchedules] = useState<ScheduleSummary[] | null>(null);
	const [listFailed, setListFailed] = useState(false);
	const [schedule, setSchedule] = useState<Schedule | null>(null);
	const [dayFailed, setDayFailed] = useState(false);
	const archive = useRef<HTMLDetailsElement>(null);

	const loadList = useCallback(() => {
		setListFailed(false);
		fetchJson<ScheduleSummary[]>("/radio/schedules")
			.then(setSchedules)
			.catch(() => setListFailed(true));
	}, []);
	useEffect(loadList, [loadList]);

	const now = new Date();
	const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
	const selected = schedules?.some((day) => day.schedule_date === selectedDate)
		? selectedDate
		: schedules?.some((day) => day.schedule_date === today)
			? today
			: (schedules?.[0]?.schedule_date ?? null);

	const load = useCallback(() => {
		if (!selected) return;
		setSchedule(null);
		setDayFailed(false);
		fetchJson<Schedule>(`/radio/schedules/${selected}`)
			.then(setSchedule)
			.catch(() => setDayFailed(true));
	}, [selected]);

	useEffect(load, [load]);

	usePageTitle(
		selected ? `Radio ${formatDate(isoDay(selected), false)}` : null,
	);

	const header = (controls?: ReactNode) => (
		<PageHeader title="Radio">{controls}</PageHeader>
	);

	if (listFailed && !schedules)
		return (
			<>
				{header()}
				<ErrorState what="radio schedules" onRetry={loadList} />
			</>
		);
	if (schedules === null)
		return (
			<>
				{header()}
				<Loading />
			</>
		);
	if (schedules.length === 0)
		return (
			<>
				{header()}
				<EmptyState title="No radio schedules have been planned yet." />
			</>
		);

	const recent = schedules.slice(0, 5);
	const older = schedules.slice(5);
	const visible = older.some((day) => day.schedule_date === selected)
		? [...recent, ...older.filter((day) => day.schedule_date === selected)]
		: recent;
	const months = [
		...new Set(older.map((day) => day.schedule_date.slice(0, 7))),
	];
	const dayItems = (days: ScheduleSummary[]) =>
		days.map((day) => ({
			key: day.schedule_date,
			href: `#radio/${day.schedule_date}`,
			label: formatDate(isoDay(day.schedule_date), false),
			title: day.schedule_date,
		}));

	return (
		<div className="radio">
			{header(
				<>
					<SegmentedLinks
						ariaLabel="Radio programmes"
						current={selected}
						items={dayItems(visible)}
						ariaCurrent="date"
						onSelect={onSelectDate}
					/>
					{older.length > 0 && (
						<details className="radio-archive" ref={archive}>
							<summary>Older programmes ({older.length})</summary>
							<div className="radio-archive-panel">
								{months.map((month) => (
									<details className="radio-archive-month" key={month}>
										<summary>{formatMonth(month)}</summary>
										<SegmentedLinks
											ariaLabel={`Programmes from ${formatMonth(month)}`}
											current={selected}
											items={dayItems(
												older.filter((day) =>
													day.schedule_date.startsWith(month),
												),
											)}
											ariaCurrent="date"
											onSelect={(date) => {
												if (archive.current) archive.current.open = false;
												onSelectDate?.(date);
											}}
										/>
									</details>
								))}
							</div>
						</details>
					)}
				</>,
			)}
			{schedule ? (
				<ScheduleDay schedule={schedule} />
			) : dayFailed ? (
				<ErrorState what="that schedule" onRetry={load} />
			) : (
				<Loading />
			)}
		</div>
	);
}

function plural(n: number, word: string) {
	return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function ScheduleDay({ schedule }: { schedule: Schedule }) {
	return (
		<>
			<div className="radio-day">
				<h2>
					<time dateTime={schedule.schedule_date}>
						{formatDate(isoDay(schedule.schedule_date))}
					</time>
				</h2>
				<span className="radio-day-meta">
					{plural(schedule.sessions.length, "session")} ·{" "}
					{duration(schedule.duration_seconds)}
				</span>
			</div>
			{schedule.note ? <p className="radio-note">{schedule.note}</p> : null}
			<div className="radio-timeline">
				{schedule.sessions.map((session) => (
					<section className="radio-session" key={session.position}>
						<span className="radio-time">
							{session.starts_at ?? "flexible"}
						</span>
						<div className="radio-session-content">
							<div className="radio-session-head">
								<h3>{session.title}</h3>
								<span className="radio-session-meta">
									{session.kind === "track_hour" ? "tracks" : "album session"} ·{" "}
									{duration(session.duration_seconds)}
								</span>
							</div>
							{session.note ? (
								<p className="radio-note">{session.note}</p>
							) : null}
							<ol className="radio-items">
								{session.items.map((item, i) => (
									<li key={item.position}>
										<span className="radio-num">{i + 1}</span>
										<span className="radio-item-name">
											{item.artist ? (
												<>
													<span className="radio-artist">{item.artist}</span>
													{" — "}
												</>
											) : null}
											{item.title}
											{item.tracks?.length ? (
												<span className="radio-tracks">
													{item.tracks.map((track) => track.title).join(" · ")}{" "}
													({plural(item.tracks.length, "track")})
												</span>
											) : null}
										</span>
										<span className="radio-dur">
											{item.duration_seconds
												? duration(item.duration_seconds)
												: "unavailable"}
										</span>
									</li>
								))}
							</ol>
						</div>
					</section>
				))}
			</div>
		</>
	);
}

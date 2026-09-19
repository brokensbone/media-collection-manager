import { useCallback, useEffect, useState } from "react";

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

function duration(seconds: number) {
	const minutes = Math.round(seconds / 60);
	return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

export function Radio() {
	const [schedules, setSchedules] = useState<ScheduleSummary[] | null>(null);
	const [selected, setSelected] = useState<string | null>(null);
	const [schedule, setSchedule] = useState<Schedule | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		fetch("/radio/schedules")
			.then((r) => (r.ok ? r.json() : Promise.reject()))
			.then((days: ScheduleSummary[]) => {
				setSchedules(days);
				setSelected(days[0]?.schedule_date ?? null);
			})
			.catch(() => setError("Couldn’t load radio schedules."));
	}, []);

	const load = useCallback(() => {
		if (!selected) return;
		setSchedule(null);
		fetch(`/radio/schedules/${selected}`)
			.then((r) => (r.ok ? r.json() : Promise.reject()))
			.then((day: Schedule) => setSchedule(day))
			.catch(() => setError("Couldn’t load that schedule."));
	}, [selected]);

	useEffect(load, [load]);

	if (error) return <p>{error}</p>;
	if (schedules === null) return <p>Loading…</p>;
	if (schedules.length === 0)
		return <p className="muted">No radio schedules have been planned yet.</p>;

	return (
		<section className="radio">
			<div className="radio-days">
				{schedules.map((day) => (
					<button
						key={day.schedule_date}
						type="button"
						className={selected === day.schedule_date ? "active" : ""}
						onClick={() => setSelected(day.schedule_date)}
					>
						{day.schedule_date}
					</button>
				))}
			</div>
			{schedule ? <ScheduleDay schedule={schedule} /> : <p>Loading…</p>}
		</section>
	);
}

function ScheduleDay({ schedule }: { schedule: Schedule }) {
	return (
		<>
			<div className="radio-head">
				<div>
					<h1>{schedule.schedule_date}</h1>
					<p className="muted">
						{schedule.sessions.length} sessions ·{" "}
						{duration(schedule.duration_seconds)}
					</p>
				</div>
			</div>
			{schedule.note ? <p className="radio-note">{schedule.note}</p> : null}
			<div className="radio-timeline">
				{schedule.sessions.map((session) => (
					<section className="radio-session" key={session.position}>
						<div className="radio-session-marker">
							<span>{session.starts_at ?? "flexible"}</span>
							<span>
								{session.kind === "track_hour" ? "tracks" : "album session"}
							</span>
						</div>
						<div className="radio-session-content">
							<h2>
								{session.title}{" "}
								<span>{duration(session.duration_seconds)}</span>
							</h2>
							{session.note ? (
								<p className="radio-note">{session.note}</p>
							) : null}
							<ol className="radio-items">
								{session.items.map((item) => (
									<li key={item.position}>
										<strong>
											{item.artist ? `${item.artist} — ` : ""}
											{item.title}
										</strong>
										<span>
											{item.duration_seconds
												? duration(item.duration_seconds)
												: "unavailable"}
										</span>
										{item.tracks?.length ? (
											<ol className="radio-tracks">
												{item.tracks.map((track) => (
													<li key={track.item_id}>{track.title}</li>
												))}
											</ol>
										) : null}
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

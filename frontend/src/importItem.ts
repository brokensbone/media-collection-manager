// The shape the /imports, /imports/tasks and /imports/archive endpoints return. Shared by the
// Import worklist, the Tasks view and the completed archive.
export type ImportState =
	| "detected"
	| "queued"
	| "importing"
	| "imported"
	| "skipped"
	| "failed";

export type ImportItem = {
	id: number;
	source: string;
	name: string;
	media_kind: "music" | "tv" | "film" | "workspace" | "unknown";
	import_target: "beets" | "tv" | "film" | "workspace" | "review";
	classification_detail: string | null;
	destination_path: string | null;
	state: ImportState;
	matched_album_id: number | null;
	matched: string | null;
	matched_owned: boolean;
	missing: boolean;
	error_detail: string | null;
	updated_at: string | null;
	created_at: string | null;
};

export function labelKind(kind: ImportItem["media_kind"]): string {
	if (kind === "tv") return "TV";
	if (kind === "film") return "Film";
	if (kind === "music") return "Music";
	if (kind === "workspace") return "Workspace";
	return "Unknown";
}

// Short and fixed-width enough to scan down a column: "14:05" today, "Sun 14:05" this week,
// "20 Nov" before that. 24-hour, no seconds; whenTitle gives the full timestamp for a tooltip.
export function whenLabel(iso: string | null, now: Date = new Date()): string {
	if (!iso) return "";
	const d = new Date(iso);
	const time = d.toLocaleTimeString("en-GB", {
		hour: "2-digit",
		minute: "2-digit",
	});
	if (d.toDateString() === now.toDateString()) return time;
	const weekAgo = new Date(now);
	weekAgo.setHours(0, 0, 0, 0);
	weekAgo.setDate(weekAgo.getDate() - 6);
	if (d >= weekAgo && d <= now)
		return `${d.toLocaleDateString("en-GB", { weekday: "short" })} ${time}`;
	return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function whenTitle(iso: string | null): string | undefined {
	if (!iso) return undefined;
	return new Date(iso).toLocaleString("en-GB", {
		weekday: "short",
		day: "numeric",
		month: "short",
		year: "numeric",
		hour: "2-digit",
		minute: "2-digit",
	});
}

// A discovery-day heading for grouping the Import list: "Today" / "Yesterday" / a plain date.
export function dayLabel(iso: string | null): string {
	if (!iso) return "Unknown date";
	const d = new Date(iso);
	const today = new Date();
	const yesterday = new Date(today);
	yesterday.setDate(today.getDate() - 1);
	if (d.toDateString() === today.toDateString()) return "Today";
	if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
	return d.toLocaleDateString(undefined, {
		day: "numeric",
		month: "short",
		year: "numeric",
	});
}

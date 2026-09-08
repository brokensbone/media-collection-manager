import type { ImportItem } from "./importItem";

export type ManualImportKind = "music" | "tv" | "film" | "workspace";

const OPTIONS: { value: ManualImportKind; label: string }[] = [
	{ value: "music", label: "Music" },
	{ value: "tv", label: "TV" },
	{ value: "film", label: "Film" },
	{ value: "workspace", label: "Workspace" },
];

export function ImportReclassify({
	item,
	onChange,
	disabled = false,
}: {
	item: ImportItem;
	onChange: () => void;
	disabled?: boolean;
}) {
	return (
		<select
			aria-label={`Classify ${item.name}`}
			value={kindValue(item)}
			disabled={disabled}
			onChange={(e) => {
				fetch(`/imports/${item.id}/classify`, {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						kind: kindTarget(e.target.value as ManualImportKind),
					}),
				}).then(onChange);
			}}
		>
			<option value="" disabled>
				Decide…
			</option>
			{OPTIONS.map((opt) => (
				<option key={opt.value} value={opt.value}>
					{opt.label}
				</option>
			))}
		</select>
	);
}

function kindValue(item: ImportItem): ManualImportKind | "" {
	if (item.import_target === "review" && item.media_kind === "unknown")
		return "";
	if (item.import_target === "workspace" || item.media_kind === "workspace")
		return "workspace";
	if (item.import_target === "tv" || item.media_kind === "tv") return "tv";
	if (item.import_target === "film" || item.media_kind === "film")
		return "film";
	return "music";
}

function kindTarget(
	kind: ManualImportKind,
): "beets" | "tv" | "film" | "workspace" {
	if (kind === "music") return "beets";
	return kind;
}

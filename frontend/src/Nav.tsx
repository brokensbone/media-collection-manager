import { useLayoutEffect, useRef } from "react";
import type { Counts, Dash } from "./Dashboard";
import { SpotifyStatus } from "./SpotifyStatus";

export type NavKey =
	| "all"
	| keyof Counts
	| "crates"
	| "radio"
	| "transmission"
	| "activity"
	| "guide";

type Item = { key: NavKey; label: string };

const FUNNEL: Item[] = [
	{ key: "all", label: "Overview" },
	{ key: "releases", label: "Releases" },
	{ key: "decide", label: "Decide" },
	{ key: "acquire", label: "Acquire" },
	{ key: "import", label: "Import" },
	{ key: "tasks", label: "Tasks" },
];
const LIBRARY: Item[] = [
	{ key: "owned", label: "Owned" },
	{ key: "dismissed", label: "Dismissed" },
];
const TOOLS: Item[] = [
	{ key: "crates", label: "Crates" },
	{ key: "radio", label: "Radio" },
	{ key: "transmission", label: "Transmission" },
	{ key: "activity", label: "Activity" },
	{ key: "guide", label: "Guide" },
];

export const NAV_LABELS: Record<NavKey, string> = Object.fromEntries(
	[...FUNNEL, ...LIBRARY, ...TOOLS].map((it) => [it.key, it.label]),
) as Record<NavKey, string>;

function count(counts: Dash | null, key: NavKey): number | undefined {
	if (!counts || !(key in counts)) return undefined;
	return counts[key as keyof Counts];
}

function Group({
	className,
	items,
	current,
	counts,
	showZero,
}: {
	className: string;
	items: Item[];
	current: NavKey;
	counts?: Dash | null;
	showZero?: boolean;
}) {
	return (
		<ul className={`nav-group ${className}`}>
			{items.map((it) => {
				const n = counts === undefined ? undefined : count(counts, it.key);
				return (
					<li key={it.key}>
						<a
							className="nav-link"
							href={`#${it.key}`}
							aria-current={it.key === current ? "page" : undefined}
						>
							{it.label}
							{n != null && (n > 0 || showZero) && (
								<>
									{" "}
									<span className="nav-count">{n}</span>
								</>
							)}
						</a>
					</li>
				);
			})}
		</ul>
	);
}

// The persistent app header. Items are real links that never relabel or move; the current one
// is marked with aria-current.
export function Nav({
	counts,
	current,
}: {
	counts: Dash | null;
	current: NavKey;
}) {
	const header = useRef<HTMLElement>(null);

	// Sticky group heads sit under the header, whose height changes when the nav wraps.
	useLayoutEffect(() => {
		const el = header.current;
		if (!el || typeof ResizeObserver === "undefined") return;
		const ro = new ResizeObserver(() => {
			document.documentElement.style.setProperty(
				"--header-h",
				`${el.offsetHeight}px`,
			);
		});
		ro.observe(el);
		return () => ro.disconnect();
	}, []);

	const total = counts ? counts.resolved + counts.unresolved : 0;

	return (
		<header className="app-header" ref={header}>
			<div className="app-header-inner">
				<a className="brand" href="#all">
					mcm
				</a>
				<nav className="main-nav" aria-label="Main">
					<Group
						className="nav-funnel"
						items={FUNNEL}
						current={current}
						counts={counts}
					/>
					<Group
						className="nav-library"
						items={LIBRARY}
						current={current}
						counts={counts}
						showZero
					/>
					<Group className="nav-tools" items={TOOLS} current={current} />
				</nav>
				<div className="header-status">
					{counts && counts.unresolved > 0 && (
						<span
							className="chip chip-info"
							title={`Resolving to MusicBrainz: ${counts.resolved}/${total} albums matched`}
						>
							<span className="chip-label">Resolving&nbsp;</span>
							{counts.resolved}/{total}
						</span>
					)}
					<SpotifyStatus />
				</div>
			</div>
		</header>
	);
}

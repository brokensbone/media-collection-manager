import "./styles.css";
import "./legacy-worklists.css";
import "./legacy-imports.css";
import "./legacy-library.css";
import "./legacy-tools.css";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { Acquire } from "./Acquire";
import { Activity } from "./Activity";
import { Crates } from "./Crates";
import { type Dash, useDashboard } from "./Dashboard";
import { Decide } from "./Decide";
import { Guide } from "./Guide";
import { parseHash, setHashPath, useHash, useQuery } from "./hashState";
import { Imports } from "./Imports";
import { shouldIgnoreKey } from "./keys";
import { Library } from "./Library";
import { NAV_LABELS, Nav, type NavKey } from "./Nav";
import { Overview } from "./Overview";
import { Owned } from "./Owned";
import { Radio } from "./Radio";
import { Releases } from "./Releases";
import { Tasks } from "./Tasks";
import { Transmission } from "./Transmission";
import { FilterBox, LiveRegion, PageHeader, usePageTitleOverride } from "./ui";

type View = NavKey | "archive";

// Views whose component renders its own PageHeader. A page group adds its views here when it
// migrates; every other view gets the temporary header below.
const MIGRATED = new Set<View>(["all"]);

// Temporary headers for views that have not migrated yet. null = the view already renders its
// own h1 (Guide, Radio), so a second one would only duplicate it.
const TEMP_HEADER: Record<View, { title: string; filter: boolean } | null> = {
	all: { title: "Overview", filter: true },
	releases: { title: "Releases", filter: true },
	decide: { title: "Decide", filter: true },
	acquire: { title: "Acquire", filter: true },
	import: { title: "Import", filter: true },
	tasks: { title: "Tasks", filter: true },
	archive: { title: "Completed archive", filter: true },
	owned: { title: "Owned", filter: true },
	dismissed: { title: "Dismissed", filter: true },
	crates: { title: "Crates", filter: false },
	radio: null,
	transmission: { title: "Transmission", filter: false },
	activity: { title: "Activity", filter: false },
	guide: null,
};

const VIEWS = new Set<string>(Object.keys(TEMP_HEADER));
const WORKLISTS = new Set<View>([
	"releases",
	"decide",
	"acquire",
	"import",
	"tasks",
]);

// Unknown paths (and the empty hash) fall back to the Overview.
function route(path: string): { view: View; radioDate: string | null } {
	const radioDate = path.match(/^radio\/(\d{4}-\d{2}-\d{2})$/)?.[1];
	if (radioDate) return { view: "radio", radioDate };
	if (VIEWS.has(path)) return { view: path as View, radioDate: null };
	return { view: "all", radioDate: null };
}

function formatDay(date: string): string {
	return new Date(`${date}T00:00:00`).toLocaleDateString("en-GB", {
		weekday: "short",
		day: "numeric",
		month: "short",
	});
}

function pageTitle(
	view: View,
	radioDate: string | null,
	counts: Dash | null,
): string {
	if (view === "archive") return "Completed archive · Tasks";
	const label = NAV_LABELS[view];
	if (view === "radio" && radioDate) return `${label} ${formatDay(radioDate)}`;
	const n = WORKLISTS.has(view) ? counts?.[view as keyof Dash] : undefined;
	return n ? `${label} (${n})` : label;
}

export default function App() {
	const path = parseHash(useHash()).path;
	const { view, radioDate } = route(path);
	const query = useQuery();
	// Any worklist action bumps this; the count/browse views refetch when it changes.
	const [refresh, setRefresh] = useState(0);
	const bump = useCallback(() => setRefresh((n) => n + 1), []);
	const counts = useDashboard(refresh);
	const titleOverride = usePageTitleOverride();

	const known = view !== "all" || path === "all";
	useEffect(() => {
		if (!known) setHashPath("all", { replace: true });
	}, [known]);

	useEffect(() => {
		document.title = `${titleOverride ?? pageTitle(view, radioDate, counts)} · mcm`;
	}, [view, radioDate, counts, titleOverride]);

	useEffect(() => {
		function onKey(e: KeyboardEvent) {
			if (e.key !== "/" || shouldIgnoreKey(e)) return;
			const input =
				document.querySelector<HTMLInputElement>("input.filter-input");
			if (!input) return;
			e.preventDefault();
			input.focus();
			input.select();
		}
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, []);

	const pages: Record<View, () => ReactNode> = {
		all: () => <Overview counts={counts} query={query} onChange={bump} />,
		releases: () => <Releases onChange={bump} query={query} />,
		decide: () => <Decide onChange={bump} query={query} />,
		acquire: () => <Acquire onChange={bump} query={query} />,
		import: () => <Imports onChange={bump} query={query} />,
		tasks: () => <Tasks onChange={bump} query={query} />,
		archive: () => <Tasks onChange={bump} query={query} archive />,
		owned: () => <Owned refreshKey={refresh} query={query} />,
		dismissed: () => (
			<Library state="dismissed" refreshKey={refresh} query={query} />
		),
		crates: () => <Crates />,
		radio: () => (
			<Radio
				selectedDate={radioDate}
				onSelectDate={(d) => setHashPath(`radio/${d}`)}
			/>
		),
		transmission: () => <Transmission />,
		activity: () => <Activity />,
		guide: () => <Guide />,
	};

	const temp = MIGRATED.has(view) ? null : TEMP_HEADER[view];

	return (
		<>
			{/* biome-ignore lint/a11y/useValidAnchor: a plain #main href would replace the route in the hash */}
			<a
				className="skip-link"
				href="#main"
				onClick={(e) => {
					// A plain #main link would replace the route in the hash.
					e.preventDefault();
					document.getElementById("main")?.focus();
				}}
			>
				Skip to content
			</a>
			<Nav counts={counts} current={view === "archive" ? "tasks" : view} />
			<main id="main" className="app" tabIndex={-1}>
				{temp && (
					<PageHeader
						title={temp.title}
						filter={temp.filter ? <FilterBox /> : undefined}
					/>
				)}
				{pages[view]()}
			</main>
			<LiveRegion />
		</>
	);
}

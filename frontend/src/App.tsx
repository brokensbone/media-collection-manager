import "./styles.css";
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
import { Shortcuts } from "./Shortcuts";
import { useScrollMemory } from "./scrollMemory";
import { Tasks } from "./Tasks";
import { Transmission } from "./Transmission";
import { LiveRegion, usePageTitleOverride } from "./ui";

type View = NavKey | "archive";

const VIEWS = new Set<string>([
	"all",
	"releases",
	"decide",
	"acquire",
	"import",
	"tasks",
	"archive",
	"owned",
	"dismissed",
	"crates",
	"radio",
	"transmission",
	"activity",
	"guide",
]);
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

// Pages that know a better title (Radio's day, a crate's name) override this with usePageTitle.
function pageTitle(view: View, counts: Dash | null): string {
	if (view === "archive") return "Completed archive · Tasks";
	const label = NAV_LABELS[view];
	const n = WORKLISTS.has(view) ? counts?.[view as keyof Dash] : undefined;
	return n ? `${label} (${n})` : label;
}

export default function App() {
	const hash = useHash();
	const path = parseHash(hash).path;
	const { view, radioDate } = route(path);
	const query = useQuery();
	// Any worklist action bumps this; the count/browse views refetch when it changes.
	const [refresh, setRefresh] = useState(0);
	const bump = useCallback(() => setRefresh((n) => n + 1), []);
	const counts = useDashboard(refresh);
	const titleOverride = usePageTitleOverride();

	useScrollMemory(hash, path);

	const known = view !== "all" || path === "all";
	useEffect(() => {
		if (!known) setHashPath("all", { replace: true });
	}, [known]);

	useEffect(() => {
		document.title = `${titleOverride ?? pageTitle(view, counts)} · mcm`;
	}, [view, counts, titleOverride]);

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
				{pages[view]()}
			</main>
			<LiveRegion />
			<Shortcuts />
		</>
	);
}

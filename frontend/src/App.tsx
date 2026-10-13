import "./styles.css";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { Acquire } from "./Acquire";
import { Activity } from "./Activity";
import { Crates } from "./Crates";
import { Dashboard, type Section } from "./Dashboard";
import { Decide } from "./Decide";
import { Guide } from "./Guide";
import { Imports } from "./Imports";
import { Library } from "./Library";
import { Owned } from "./Owned";
import { Radio } from "./Radio";
import { Releases } from "./Releases";
import { SpotifyStatus } from "./SpotifyStatus";
import { Tasks } from "./Tasks";
import { Transmission } from "./Transmission";

// 'archive' is the completed-imports archive — reached only from a link inside the Tasks view,
// not the tile row or the top nav.
type View =
	| "app"
	| "guide"
	| "transmission"
	| "activity"
	| "archive"
	| "crates"
	| "radio";

const SECTIONS: Section[] = [
	"all",
	"releases",
	"decide",
	"acquire",
	"import",
	"tasks",
	"owned",
	"dismissed",
];

// The active tab lives in the URL hash (#guide, #transmission, #acquire, …) so a refresh or
// a shared link restores the same view. A view may carry a query (e.g. #tasks?log=42 deep-links
// a failure log), so match on the path part before '?'.
function readHash(): {
	view: View;
	section: Section;
	radioDate: string | null;
} {
	const h = window.location.hash.replace(/^#/, "").split("?")[0];
	if (h === "guide") return { view: "guide", section: "all", radioDate: null };
	if (h === "transmission")
		return { view: "transmission", section: "all", radioDate: null };
	if (h === "activity")
		return { view: "activity", section: "all", radioDate: null };
	if (h === "archive")
		return { view: "archive", section: "all", radioDate: null };
	if (h === "crates")
		return { view: "crates", section: "all", radioDate: null };
	if (h === "radio") return { view: "radio", section: "all", radioDate: null };
	const radioDate = h.match(/^radio\/(\d{4}-\d{2}-\d{2})$/)?.[1];
	if (radioDate) return { view: "radio", section: "all", radioDate };
	if ((SECTIONS as string[]).includes(h))
		return { view: "app", section: h as Section, radioDate: null };
	return { view: "app", section: "all", radioDate: null };
}

export default function App() {
	const [view, setView] = useState<View>(() => readHash().view);
	const [section, setSection] = useState<Section>(() => readHash().section);
	const [radioDate, setRadioDate] = useState<string | null>(
		() => readHash().radioDate,
	);
	const [query, setQuery] = useState("");

	useEffect(() => {
		const target =
			view === "app"
				? section
				: view === "radio" && radioDate
					? `radio/${radioDate}`
					: view;
		// Compare only the path part: a view is free to keep its own query (e.g. #tasks?log=42), and
		// rewriting it here would clobber that. Only write when the actual view/section changed.
		if (window.location.hash.replace(/^#/, "").split("?")[0] !== target) {
			window.location.hash = target;
		}
	}, [view, section, radioDate]);

	useEffect(() => {
		function onHash() {
			const r = readHash();
			setView(r.view);
			setSection(r.section);
			setRadioDate(r.radioDate);
			if (r.section === "import" && window.location.hash.includes("?item="))
				setQuery("");
		}
		window.addEventListener("hashchange", onHash);
		return () => window.removeEventListener("hashchange", onHash);
	}, []);
	// Any worklist action bumps this; the count/browse views refetch when it changes.
	const [refresh, setRefresh] = useState(0);
	const bump = useCallback(() => setRefresh((n) => n + 1), []);

	const sections: { key: Section; heading: string; node: ReactNode }[] = [
		{
			key: "releases",
			heading: "Releases",
			node: <Releases onChange={bump} query={query} />,
		},
		{
			key: "decide",
			heading: "Decide",
			node: <Decide onChange={bump} query={query} />,
		},
		{
			key: "acquire",
			heading: "Acquire",
			node: <Acquire onChange={bump} query={query} />,
		},
		{
			key: "import",
			heading: "Import",
			node: <Imports onChange={bump} query={query} />,
		},
		{
			key: "tasks",
			heading: "Tasks",
			node: <Tasks onChange={bump} query={query} />,
		},
		{
			key: "owned",
			heading: "Owned",
			node: <Owned refreshKey={refresh} query={query} />,
		},
		{
			key: "dismissed",
			heading: "Dismissed",
			node: <Library state="dismissed" refreshKey={refresh} query={query} />,
		},
	];

	return (
		<div className="app">
			<header className="topbar">
				<span className="brand">mcm</span>
				<div className="topbar-right">
					<button
						type="button"
						className="linklike"
						onClick={() => {
							if (view === "radio") {
								setView("app");
							} else {
								setRadioDate(null);
								setView("radio");
							}
						}}
					>
						{view === "radio" ? "Dashboard" : "Radio"}
					</button>
					<button
						type="button"
						className="linklike"
						onClick={() => setView(view === "guide" ? "app" : "guide")}
					>
						{view === "guide" ? "Dashboard" : "Guide"}
					</button>
					<button
						type="button"
						className="linklike"
						onClick={() =>
							setView(view === "transmission" ? "app" : "transmission")
						}
					>
						{view === "transmission" ? "Dashboard" : "Transmission"}
					</button>
					<button
						type="button"
						className="linklike"
						onClick={() => setView(view === "activity" ? "app" : "activity")}
					>
						{view === "activity" ? "Dashboard" : "Activity"}
					</button>
					<button
						type="button"
						className="linklike"
						onClick={() => setView(view === "crates" ? "app" : "crates")}
					>
						{view === "crates" ? "Dashboard" : "Crates"}
					</button>
					<SpotifyStatus />
				</div>
			</header>
			{view === "guide" ? (
				<Guide />
			) : view === "transmission" ? (
				<Transmission />
			) : view === "activity" ? (
				<Activity />
			) : view === "crates" ? (
				<Crates />
			) : view === "radio" ? (
				<Radio selectedDate={radioDate} onSelectDate={setRadioDate} />
			) : view === "archive" ? (
				<section>
					<h2>Completed archive</h2>
					<Tasks onChange={bump} archive />
				</section>
			) : (
				<>
					<Dashboard
						refreshKey={refresh}
						active={section}
						onSelect={setSection}
					/>
					<input
						type="search"
						className="filter"
						placeholder="filter by artist or title…"
						value={query}
						onChange={(e) => setQuery(e.target.value)}
					/>
					{sections
						.filter((s) => section === "all" || s.key === section)
						.map((s) => (
							<section key={s.key}>
								<h2>{s.heading}</h2>
								{s.node}
							</section>
						))}
				</>
			)}
		</div>
	);
}

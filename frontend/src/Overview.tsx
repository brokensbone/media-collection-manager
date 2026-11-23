import type { ReactNode } from "react";
import { Acquire } from "./Acquire";
import type { Counts, Dash } from "./Dashboard";
import { Decide } from "./Decide";
import { Imports } from "./Imports";
import { Releases } from "./Releases";
import { Tasks } from "./Tasks";
import { FilterBox, GroupHead, PageHeader } from "./ui";

export const OVERVIEW_LIMIT = 5;

// Where work is waiting: the five funnel sections, each capped at a few rows.
export function Overview({
	counts,
	query,
	onChange,
}: {
	counts: Dash | null;
	query: string;
	onChange: () => void;
}) {
	const limit = OVERVIEW_LIMIT;
	const sections: { key: keyof Counts; title: string; node: ReactNode }[] = [
		{
			key: "releases",
			title: "Releases",
			node: <Releases onChange={onChange} query={query} limit={limit} />,
		},
		{
			key: "decide",
			title: "Decide",
			node: <Decide onChange={onChange} query={query} limit={limit} />,
		},
		{
			key: "acquire",
			title: "Acquire",
			node: <Acquire onChange={onChange} query={query} limit={limit} />,
		},
		{
			key: "import",
			title: "Import",
			node: <Imports onChange={onChange} query={query} limit={limit} />,
		},
		{
			key: "tasks",
			title: "Tasks",
			node: <Tasks onChange={onChange} query={query} limit={limit} />,
		},
	];

	return (
		<>
			<PageHeader title="Overview" filter={<FilterBox />} />
			{sections.map((s) => {
				// Unknown (not yet loaded) counts still render the section; only a known zero collapses it.
				const n = counts?.[s.key];
				return (
					<section key={s.key} className="overview-section">
						<GroupHead title={s.title} count={n}>
							{n != null && n > 0 && <a href={`#${s.key}`}>See all {n} →</a>}
						</GroupHead>
						{n === 0 ? (
							<p className="state-inline">Nothing waiting.</p>
						) : (
							s.node
						)}
					</section>
				);
			})}
		</>
	);
}

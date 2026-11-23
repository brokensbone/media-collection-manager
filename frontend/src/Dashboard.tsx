import { useEffect, useState } from "react";
import { fetchJson } from "./api";

export type Counts = {
	releases: number;
	decide: number;
	acquire: number;
	import: number;
	tasks: number;
	owned: number;
	dismissed: number;
};

export type Section = "all" | keyof Counts;

// The counts payload also carries cold-start resolution progress, which isn't a section.
export type Dash = Counts & { resolved: number; unresolved: number };

// The /dashboard counts behind the nav, the Overview and the page titles. A failed refetch keeps
// the last counts rather than blanking the nav.
export function useDashboard(refreshKey = 0): Dash | null {
	const [counts, setCounts] = useState<Dash | null>(null);

	// biome-ignore lint/correctness/useExhaustiveDependencies: refreshKey is a manual refetch trigger
	useEffect(() => {
		let live = true;
		fetchJson<Dash>("/dashboard")
			.then((d) => live && setCounts(d))
			.catch(() => {});
		return () => {
			live = false;
		};
	}, [refreshKey]);

	return counts;
}

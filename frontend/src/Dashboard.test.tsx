import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useDashboard } from "./Dashboard";
import { Nav, type NavKey } from "./Nav";

function Shell({
	refreshKey = 0,
	current = "all",
}: {
	refreshKey?: number;
	current?: NavKey;
}) {
	return <Nav counts={useDashboard(refreshKey)} current={current} />;
}

function stubCounts(counts: Record<string, number>) {
	const fetchMock = vi.fn((url: string) =>
		Promise.resolve({
			json: () =>
				Promise.resolve(url === "/dashboard" ? counts : { connected: false }),
		}),
	);
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
});

describe("Nav", () => {
	it("shows the worklist counts in the nav links", async () => {
		stubCounts({
			releases: 1,
			decide: 3,
			acquire: 12,
			import: 5,
			tasks: 0,
			owned: 40,
			dismissed: 2,
			resolved: 0,
			unresolved: 0,
		});
		render(<Shell />);
		expect(await screen.findByRole("link", { name: "Decide 3" })).toBeTruthy();
		expect(screen.getByRole("link", { name: "Acquire 12" })).toBeTruthy();
		expect(screen.getByRole("link", { name: "Import 5" })).toBeTruthy();
		expect(screen.getByRole("link", { name: "Owned 40" })).toBeTruthy();
		// a zero funnel count is hidden
		expect(screen.getByRole("link", { name: "Tasks" })).toBeTruthy();
	});

	it("renders every link immediately, before the counts load", () => {
		vi.stubGlobal(
			"fetch",
			vi.fn(() => new Promise(() => {})),
		);
		render(<Shell />);
		expect(screen.getByRole("link", { name: "Decide" })).toBeTruthy();
		expect(screen.getByRole("link", { name: "Owned" })).toBeTruthy();
		expect(screen.getByRole("link", { name: "Overview" })).toBeTruthy();
		expect(screen.getByRole("link", { name: "Guide" })).toBeTruthy();
	});

	it("refetches its counts when refreshKey changes", async () => {
		const fetchMock = stubCounts({ decide: 1 });
		const { rerender } = render(<Shell refreshKey={0} />);
		await screen.findByRole("link", { name: "Decide 1" });
		const dashboardCalls = () =>
			fetchMock.mock.calls.filter(([url]) => url === "/dashboard").length;
		expect(dashboardCalls()).toBe(1);
		rerender(<Shell refreshKey={1} />);
		await waitFor(() => expect(dashboardCalls()).toBe(2));
	});

	it("marks the current view and never relabels", () => {
		vi.stubGlobal(
			"fetch",
			vi.fn(() => new Promise(() => {})),
		);
		const { rerender } = render(<Shell current="guide" />);
		const guide = screen.getByRole("link", { name: "Guide" });
		expect(guide.getAttribute("aria-current")).toBe("page");
		expect(guide.getAttribute("href")).toBe("#guide");
		expect(
			screen
				.getByRole("link", { name: "Overview" })
				.getAttribute("aria-current"),
		).toBeNull();
		rerender(<Shell current="tasks" />);
		expect(
			screen.getByRole("link", { name: "Guide" }).getAttribute("aria-current"),
		).toBeNull();
		expect(
			screen.getByRole("link", { name: "Tasks" }).getAttribute("aria-current"),
		).toBe("page");
		expect(screen.queryByText("Dashboard")).toBeNull();
	});

	it("shows resolving progress as a chip", async () => {
		stubCounts({ decide: 0, resolved: 76, unresolved: 37 });
		render(<Shell />);
		const chip = await screen.findByTitle(
			"Resolving to MusicBrainz: 76/113 albums matched",
		);
		expect(chip.textContent).toContain("76/113");
	});
});

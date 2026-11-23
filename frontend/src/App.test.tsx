import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
	within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function stubFetch() {
	const counts = {
		releases: 0,
		decide: 0,
		acquire: 0,
		import: 0,
		owned: 0,
		dismissed: 0,
	};
	vi.stubGlobal(
		"fetch",
		vi.fn((url: string) =>
			Promise.resolve({
				json: () => Promise.resolve(url === "/dashboard" ? counts : []),
			}),
		),
	);
}

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	window.location.hash = "";
});

describe("App", () => {
	it("renders the app name", () => {
		stubFetch();
		render(<App />);
		expect(screen.getByText("mcm")).toBeTruthy();
	});

	it("opens the guide from the nav and goes back to the overview", async () => {
		stubFetch();
		render(<App />);
		fireEvent.click(screen.getByRole("link", { name: "Guide" }));
		expect(await screen.findByRole("heading", { name: "Guide" })).toBeTruthy();
		// the nav never relabels: Guide is still there, now marked current
		expect(
			screen.getByRole("link", { name: "Guide" }).getAttribute("aria-current"),
		).toBe("page");
		fireEvent.click(screen.getByRole("link", { name: "Overview" }));
		await waitFor(() =>
			expect(screen.queryByRole("heading", { name: "Guide" })).toBeNull(),
		);
	});

	it("opens a dated radio programme from its direct URL", async () => {
		window.location.hash = "radio/2026-09-22";
		vi.stubGlobal(
			"fetch",
			vi.fn((url: string) =>
				Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve(
							url === "/radio/schedules"
								? [
										{
											schedule_date: "2026-09-22",
											note: null,
											session_count: 0,
											duration_seconds: 0,
										},
									]
								: {
										schedule_date: "2026-09-22",
										note: null,
										session_count: 0,
										duration_seconds: 0,
										sessions: [],
									},
						),
				}),
			),
		);

		render(<App />);
		expect(
			await screen.findByRole("heading", { name: "Tue 22 Sep 2026" }),
		).toBeTruthy();
		expect(fetch).toHaveBeenCalledWith("/radio/schedules/2026-09-22");
	});

	it("keeps the clicked radio date in the URL and across a reload", async () => {
		window.location.hash = "radio";
		vi.stubGlobal(
			"fetch",
			vi.fn((url: string) =>
				Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve(
							url === "/radio/schedules"
								? ["2026-09-25", "2026-09-22"].map((schedule_date) => ({
										schedule_date,
										note: null,
										session_count: 0,
										duration_seconds: 0,
									}))
								: {
										schedule_date: url.split("/").at(-1),
										note: null,
										session_count: 0,
										duration_seconds: 0,
										sessions: [],
									},
						),
				}),
			),
		);

		const page = render(<App />);
		fireEvent.click(await screen.findByRole("link", { name: "Tue 22 Sep" }));
		await waitFor(() => expect(window.location.hash).toBe("#radio/2026-09-22"));
		page.unmount();
		render(<App />);
		expect(
			await screen.findByRole("heading", { name: "Tue 22 Sep 2026" }),
		).toBeTruthy();
	});

	it("filters the visible tables as you type", async () => {
		const counts = {
			releases: 0,
			decide: 0,
			acquire: 2,
			import: 0,
			owned: 0,
			dismissed: 0,
		};
		const acquire = [
			{
				id: 1,
				artist: "Porridge Radio",
				title: "Every Bad",
				has_art: false,
				bandcamp_url: "x",
			},
			{
				id: 2,
				artist: "Burial",
				title: "Untrue",
				has_art: false,
				bandcamp_url: "x",
			},
		];
		vi.stubGlobal(
			"fetch",
			vi.fn((url: string) =>
				Promise.resolve({
					json: () =>
						Promise.resolve(
							url === "/dashboard" ? counts : url === "/acquire" ? acquire : [],
						),
				}),
			),
		);
		render(<App />);
		expect(await screen.findByText("Every Bad")).toBeTruthy();
		expect(screen.getByText("Untrue")).toBeTruthy();

		fireEvent.change(screen.getByPlaceholderText(/filter/i), {
			target: { value: "porri ev" },
		});
		expect(screen.getByText("Every Bad")).toBeTruthy();
		expect(screen.queryByText("Untrue")).toBeNull();
		// the filter lives in the URL, so a reload keeps it
		expect(window.location.hash).toBe("#all?q=porri+ev");
	});

	it("drops the filter when the nav changes view", async () => {
		stubFetch();
		window.location.hash = "decide?q=zzz";
		render(<App />);
		expect(
			(screen.getByRole("searchbox", { name: "Filter" }) as HTMLInputElement)
				.value,
		).toBe("zzz");
		fireEvent.click(screen.getByRole("link", { name: /Acquire/ }));
		await waitFor(() => expect(window.location.hash).toBe("#acquire"));
		expect(
			(screen.getByRole("searchbox", { name: "Filter" }) as HTMLInputElement)
				.value,
		).toBe("");
	});

	it("focuses the filter on / and clears it on Esc", () => {
		stubFetch();
		window.location.hash = "decide?q=abc";
		render(<App />);
		const input = screen.getByRole("searchbox", {
			name: "Filter",
		}) as HTMLInputElement;
		fireEvent.keyDown(document.body, { key: "/" });
		expect(document.activeElement).toBe(input);
		fireEvent.keyDown(input, { key: "Escape" });
		expect(input.value).toBe("");
		expect(window.location.hash).toBe("#decide");
		fireEvent.keyDown(input, { key: "Escape" });
		expect(document.activeElement).not.toBe(input);
	});

	it("marks Tasks current on the archive and sets the page title", async () => {
		stubFetch();
		window.location.hash = "archive";
		render(<App />);
		expect(
			screen.getByRole("link", { name: "Tasks" }).getAttribute("aria-current"),
		).toBe("page");
		expect(document.title).toBe("Completed archive · Tasks · mcm");
	});

	it("puts the worklist count in the page title", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn((url: string) =>
				Promise.resolve({
					json: () =>
						Promise.resolve(
							url === "/dashboard"
								? { decide: 26, resolved: 0, unresolved: 0 }
								: [],
						),
				}),
			),
		);
		window.location.hash = "decide";
		render(<App />);
		await waitFor(() => expect(document.title).toBe("Decide (26) · mcm"));
	});

	it("has one main landmark, a skip link and an h1", () => {
		stubFetch();
		render(<App />);
		expect(screen.getByRole("main")).toBeTruthy();
		expect(screen.getByRole("navigation", { name: "Main" })).toBeTruthy();
		expect(screen.getByRole("link", { name: "Skip to content" })).toBeTruthy();
		expect(
			screen.getAllByRole("heading", { level: 1 }).map((h) => h.textContent),
		).toEqual(["Overview"]);
	});

	it("shows the five funnel sections on the overview, capped, with See all links", async () => {
		const releases = Array.from({ length: 8 }, (_, i) => ({
			id: i + 1,
			artist: `Artist ${i + 1}`,
			title: `Title ${i + 1}`,
			has_art: false,
			spotify_id: null,
			album_type: null,
		}));
		vi.stubGlobal(
			"fetch",
			vi.fn((url: string) =>
				Promise.resolve({
					json: () =>
						Promise.resolve(
							url === "/dashboard"
								? {
										releases: 8,
										decide: 0,
										acquire: 0,
										import: 0,
										tasks: 0,
										owned: 3,
										dismissed: 1,
										resolved: 0,
										unresolved: 0,
									}
								: url === "/releases"
									? releases
									: [],
						),
				}),
			),
		);
		render(<App />);
		expect(await screen.findByText("Title 5")).toBeTruthy();
		expect(screen.queryByText("Title 6")).toBeNull();
		expect(
			screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent),
		).toEqual(["Releases", "Decide", "Acquire", "Import", "Tasks"]);
		const seeAll = screen.getByRole("link", { name: "See all 8 →" });
		expect(seeAll.getAttribute("href")).toBe("#releases");
		await waitFor(() =>
			expect(screen.getAllByText("Nothing waiting.")).toHaveLength(4),
		);
	});

	it("filters to a single worklist when a dashboard label is clicked", async () => {
		stubFetch();
		render(<App />);
		// all sections shown to start
		expect(
			await screen.findByRole("heading", { name: "Releases" }),
		).toBeTruthy();
		expect(screen.getByRole("heading", { name: "Acquire" })).toBeTruthy();
		// click the Decide nav link → only Decide remains
		fireEvent.click(
			within(screen.getByRole("navigation", { name: "Main" })).getByRole(
				"link",
				{ name: /Decide/ },
			),
		);
		await waitFor(() =>
			expect(screen.queryByRole("heading", { name: "Releases" })).toBeNull(),
		);
		expect(
			screen.getByRole("heading", { level: 1, name: "Decide" }),
		).toBeTruthy();
		expect(screen.queryByRole("heading", { name: "Acquire" })).toBeNull();
	});
});

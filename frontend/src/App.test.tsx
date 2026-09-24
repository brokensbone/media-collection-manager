import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
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

	it("toggles to the guide from the top bar and back", () => {
		stubFetch();
		render(<App />);
		fireEvent.click(screen.getByRole("button", { name: "Guide" }));
		expect(screen.getByRole("heading", { name: "How mcm works" })).toBeTruthy();
		fireEvent.click(screen.getByRole("button", { name: "Dashboard" }));
		expect(screen.queryByRole("heading", { name: "How mcm works" })).toBeNull();
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
			await screen.findByRole("heading", { name: "2026-09-22" }),
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
		fireEvent.click(await screen.findByRole("link", { name: "2026-09-22" }));
		await waitFor(() => expect(window.location.hash).toBe("#radio/2026-09-22"));
		page.unmount();
		render(<App />);
		expect(
			await screen.findByRole("heading", { name: "2026-09-22" }),
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
	});

	it("filters to a single worklist when a dashboard label is clicked", async () => {
		stubFetch();
		render(<App />);
		// all sections shown to start
		expect(
			await screen.findByRole("heading", { name: "Releases" }),
		).toBeTruthy();
		expect(screen.getByRole("heading", { name: "Acquire" })).toBeTruthy();
		// click the "decide" label → only Decide remains
		fireEvent.click(screen.getByRole("button", { name: /decide/ }));
		expect(screen.getByRole("heading", { name: "Decide" })).toBeTruthy();
		expect(screen.queryByRole("heading", { name: "Releases" })).toBeNull();
		expect(screen.queryByRole("heading", { name: "Acquire" })).toBeNull();
	});
});

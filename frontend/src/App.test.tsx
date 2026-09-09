import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
		expect(
			screen.getByRole("heading", { name: "How mcm works" }),
		).toBeTruthy();
		fireEvent.click(screen.getByRole("button", { name: "Dashboard" }));
		expect(
			screen.queryByRole("heading", { name: "How mcm works" }),
		).toBeNull();
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

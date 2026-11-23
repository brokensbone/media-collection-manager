import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Activity } from "./Activity";

afterEach(() => {
	cleanup();
	window.location.hash = "";
	vi.unstubAllGlobals();
});

describe("Activity", () => {
	it("renders worker events with their job and message", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn(() =>
				Promise.resolve({
					json: () =>
						Promise.resolve([
							{
								id: 1,
								created_at: "2026-07-22T10:00:00Z",
								job: "resolution",
								type: "resolved",
								message: "Resolved 'A — B'",
								album_id: 7,
							},
						]),
				}),
			),
		);
		const { container } = render(<Activity />);
		await screen.findByText("Resolved 'A — B'");
		expect(container.textContent).toContain("resolution");
	});

	it("shows an empty state before any events", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn(() => Promise.resolve({ json: () => Promise.resolve([]) })),
		);
		render(<Activity />);
		expect(await screen.findByText(/No worker activity/)).toBeTruthy();
	});

	it("groups by day, badges errors and filters to errors only", async () => {
		window.location.hash = "#activity";
		const now = new Date();
		const yesterday = new Date(now.getTime() - 24 * 3600 * 1000);
		vi.stubGlobal(
			"fetch",
			vi.fn(() =>
				Promise.resolve({
					json: () =>
						Promise.resolve([
							{
								id: 1,
								created_at: yesterday.toISOString(),
								job: "import",
								type: "imported",
								message: "Imported 'C'",
								album_id: null,
							},
							{
								id: 2,
								created_at: now.toISOString(),
								job: "resolution",
								type: "error",
								message: "Couldn't reach MusicBrainz",
								album_id: null,
							},
						]),
				}),
			),
		);
		render(<Activity />);
		const message = await screen.findByText("Couldn't reach MusicBrainz");
		expect(message.parentElement?.textContent).toContain("error");
		expect(screen.getByRole("heading", { name: "Today" })).toBeTruthy();
		expect(screen.getByRole("heading", { name: "Yesterday" })).toBeTruthy();

		fireEvent.click(screen.getByRole("button", { name: "Errors 1" }));
		expect(window.location.hash).toBe("#activity?show=errors");
		expect(screen.queryByText("Imported 'C'")).toBeNull();
		expect(screen.getByText("Couldn't reach MusicBrainz")).toBeTruthy();
	});

	it("shows an error with Retry when the first load fails", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn(() => Promise.reject(new Error("down"))),
		);
		render(<Activity />);
		expect(await screen.findByText("Couldn’t load activity.")).toBeTruthy();
		expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
		expect(screen.queryByText(/No worker activity/)).toBeNull();
	});
});

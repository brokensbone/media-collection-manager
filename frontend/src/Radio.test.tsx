import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Radio } from "./Radio";

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
});

describe("Radio", () => {
	it("shows a dated schedule with marked session boundaries and notes", async () => {
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
											schedule_date: "2026-09-21",
											note: "Monday shape",
											session_count: 2,
											duration_seconds: 7200,
										},
									]
								: {
										schedule_date: "2026-09-21",
										note: "Monday shape",
										session_count: 2,
										duration_seconds: 7200,
										sessions: [
											{
												position: 0,
												kind: "track_hour",
												title: "Morning club warm-up",
												starts_at: "09:00",
												note: "Gentle pulse.",
												duration_seconds: 3600,
												items: [],
											},
										],
									},
						),
				}),
			),
		);

		render(<Radio selectedDate={null} />);
		expect(await screen.findByText("Morning club warm-up")).toBeTruthy();
		expect(screen.getByText("09:00")).toBeTruthy();
		expect(screen.getByText("Gentle pulse.")).toBeTruthy();
		await waitFor(() =>
			expect(fetch).toHaveBeenCalledWith("/radio/schedules/2026-09-21"),
		);
	});

	it("gives every programme day a direct link", async () => {
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
											schedule_date: "2026-09-21",
											note: null,
											session_count: 0,
											duration_seconds: 0,
										},
									]
								: {
										schedule_date: "2026-09-21",
										note: null,
										session_count: 0,
										duration_seconds: 0,
										sessions: [],
									},
						),
				}),
			),
		);

		render(<Radio selectedDate={null} />);
		expect(
			(await screen.findByRole("link", { name: "2026-09-21" })).getAttribute(
				"href",
			),
		).toBe("#radio/2026-09-21");
	});

	it("opens today's programme by default when later dates are scheduled", async () => {
		const now = new Date();
		const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
		const tomorrow = new Date(
			now.getFullYear(),
			now.getMonth(),
			now.getDate() + 1,
		);
		const later = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, "0")}-${String(tomorrow.getDate()).padStart(2, "0")}`;
		vi.stubGlobal(
			"fetch",
			vi.fn((url: string) =>
				Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve(
							url === "/radio/schedules"
								? [later, today].map((schedule_date) => ({
										schedule_date,
										note: null,
										session_count: 0,
										duration_seconds: 0,
									}))
								: {
										schedule_date: today,
										note: null,
										session_count: 0,
										duration_seconds: 0,
										sessions: [],
									},
						),
				}),
			),
		);

		render(<Radio selectedDate={null} />);
		await waitFor(() =>
			expect(fetch).toHaveBeenCalledWith(`/radio/schedules/${today}`),
		);
	});
});

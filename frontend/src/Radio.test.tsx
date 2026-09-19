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

		render(<Radio />);
		expect(await screen.findByText("Morning club warm-up")).toBeTruthy();
		expect(screen.getByText("09:00")).toBeTruthy();
		expect(screen.getByText("Gentle pulse.")).toBeTruthy();
		await waitFor(() =>
			expect(fetch).toHaveBeenCalledWith("/radio/schedules/2026-09-21"),
		);
	});
});

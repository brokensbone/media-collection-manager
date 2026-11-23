import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { duration, Radio } from "./Radio";

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
});

describe("Radio", () => {
	it("keeps older schedules in a month archive and supports direct links", async () => {
		const dates = [
			"2026-11-19",
			"2026-11-17",
			"2026-11-16",
			"2026-11-14",
			"2026-11-12",
			"2026-10-30",
		];
		vi.stubGlobal(
			"fetch",
			vi.fn((url: string) =>
				Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve(
							url === "/radio/schedules"
								? dates.map((schedule_date) => ({
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
		const { rerender } = render(<Radio selectedDate={null} />);
		const archive = await screen.findByText("Older programmes (1)");
		expect(archive.closest("details")?.open).toBe(false);
		fireEvent.click(archive);
		fireEvent.click(screen.getByText("Oct 2026"));
		expect(
			screen.getByRole("link", { name: "Fri 30 Oct" }).getAttribute("href"),
		).toBe("#radio/2026-10-30");
		rerender(<Radio selectedDate="2026-10-30" />);
		await waitFor(() =>
			expect(fetch).toHaveBeenCalledWith("/radio/schedules/2026-10-30"),
		);
	});
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
			(await screen.findByRole("link", { name: "Mon 21 Sep" })).getAttribute(
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

	it("titles the page Radio and the day with a formatted date", async () => {
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
											session_count: 1,
											duration_seconds: 2880,
										},
									]
								: {
										schedule_date: "2026-09-21",
										note: null,
										session_count: 1,
										duration_seconds: 2880,
										sessions: [
											{
												position: 0,
												kind: "album_session",
												title: "Album hour",
												starts_at: "10:00",
												note: null,
												duration_seconds: 2880,
												items: [
													{
														position: 0,
														kind: "album",
														beets_id: "1",
														item_id: null,
														artist: "Burial",
														title: "Untrue",
														duration_seconds: 2880,
														tracks: [
															{ item_id: "a", title: "Archangel" },
															{ item_id: "b", title: "Near Dark" },
														],
													},
												],
											},
										],
									},
						),
				}),
			),
		);
		render(<Radio selectedDate={null} />);
		expect(
			screen.getByRole("heading", { level: 1, name: "Radio" }),
		).toBeTruthy();
		expect(
			await screen.findByRole("heading", { level: 2, name: "Mon 21 Sep 2026" }),
		).toBeTruthy();
		expect(
			screen.getByRole("heading", { level: 3, name: "Album hour" }),
		).toBeTruthy();
		expect(screen.getByText("Burial")).toBeTruthy();
		expect(screen.getByText(/Archangel · Near Dark \(2 tracks\)/)).toBeTruthy();
		expect(
			screen
				.getByRole("link", { name: "Mon 21 Sep" })
				.getAttribute("aria-current"),
		).toBe("date");
	});

	it("shows an error with Retry when the schedules fail to load", async () => {
		const fetchMock = vi.fn(() => Promise.resolve({ ok: false, status: 500 }));
		vi.stubGlobal("fetch", fetchMock);
		render(<Radio selectedDate={null} />);
		expect(
			await screen.findByText("Couldn’t load radio schedules."),
		).toBeTruthy();
		fireEvent.click(screen.getByRole("button", { name: "Retry" }));
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});
});

describe("duration", () => {
	it("prints minutes under an hour and hours with minutes otherwise", () => {
		expect(duration(420)).toBe("7m");
		expect(duration(4620)).toBe("1h 17m");
		expect(duration(3720)).toBe("1h 02m");
	});
});

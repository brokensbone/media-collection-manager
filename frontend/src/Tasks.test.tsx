import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Tasks } from "./Tasks";

function mockApi(items: unknown) {
	const fetchMock = vi.fn(
		(_url: string, opts?: { method?: string; body?: string }) =>
			opts?.method
				? Promise.resolve({ ok: true })
				: Promise.resolve({ json: () => Promise.resolve(items) }),
	);
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

function item(over: Record<string, unknown> = {}) {
	return {
		id: 1,
		source: "transmission",
		name: "Thing",
		media_kind: "film",
		import_target: "film",
		classification_detail: null,
		destination_path: null,
		state: "imported",
		matched_album_id: null,
		matched: null,
		matched_owned: false,
		missing: false,
		error_detail: null,
		updated_at: "2026-07-27T12:00:00+00:00",
		...over,
	};
}

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	window.location.hash = "";
});

describe("Tasks", () => {
	it("groups rows by status", async () => {
		mockApi([
			item({ id: 1, name: "Running", state: "importing" }),
			item({ id: 2, name: "Waiting", state: "queued" }),
			item({ id: 3, name: "Broke", state: "failed" }),
			item({ id: 4, name: "Done", state: "imported" }),
		]);
		render(<Tasks />);
		await screen.findByText("Running");
		expect(screen.getByText("In progress")).toBeTruthy();
		expect(screen.getByText("Queued")).toBeTruthy();
		expect(screen.getByText("Failed")).toBeTruthy();
		expect(screen.getByText("Completed")).toBeTruthy();
		expect(screen.getByText("imported ✓")).toBeTruthy();
	});

	it("fetches from /imports/tasks and offers an archive link", async () => {
		const fetchMock = mockApi([
			item({ id: 1, name: "Done", state: "imported" }),
		]);
		render(<Tasks />);
		await screen.findByText("Done");
		expect(fetchMock.mock.calls[0][0]).toBe("/imports/tasks");
		expect(
			screen.getByRole("button", { name: /View completed archive/ }),
		).toBeTruthy();
	});

	it("lets a failed task reveal its log, then retry", async () => {
		const fetchMock = mockApi([
			item({
				id: 5,
				name: "Bad.mkv",
				state: "failed",
				error_detail: "TimeoutExpired: rsync timed out after 1800 seconds",
			}),
		]);
		render(<Tasks />);
		await screen.findByText("failed");
		expect(screen.queryByText(/timed out after 1800/)).toBeNull();
		fireEvent.click(screen.getByRole("button", { name: "Log" }));
		expect(screen.getByText(/timed out after 1800/)).toBeTruthy();

		fireEvent.click(screen.getByRole("button", { name: "Retry" }));
		const posted = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
		expect(posted?.[0]).toBe("/imports/5/import");
	});

	it("lets a queued task be reclassified", async () => {
		const fetchMock = mockApi([item({ id: 6, name: "Pack", state: "queued" })]);
		render(<Tasks />);
		await screen.findByText("Pack");
		fireEvent.change(screen.getByRole("combobox", { name: "Classify Pack" }), {
			target: { value: "workspace" },
		});

		const posted = fetchMock.mock.calls.find(
			(c) => c[0] === "/imports/6/classify",
		);
		expect(posted?.[1]?.method).toBe("POST");
		expect(posted?.[1]?.body).toBe(JSON.stringify({ kind: "workspace" }));
	});

	it("mirrors an opened failure log into the URL for sharing", async () => {
		window.location.hash = "tasks";
		mockApi([
			item({
				id: 5,
				name: "Bad.mkv",
				state: "failed",
				error_detail: "the reason",
			}),
		]);
		render(<Tasks />);
		await screen.findByText("failed");
		fireEvent.click(screen.getByRole("button", { name: "Log" }));
		expect(window.location.hash).toBe("#tasks?log=5");
		expect(screen.getByText("the reason")).toBeTruthy();
		fireEvent.click(screen.getByRole("button", { name: "Hide log" }));
		expect(window.location.hash).toBe("#tasks");
	});

	it("opens the deep-linked failure log named in the URL on load", async () => {
		window.location.hash = "tasks?log=7";
		mockApi([
			item({
				id: 7,
				name: "Bad.mkv",
				state: "failed",
				error_detail: "the deep reason",
			}),
		]);
		render(<Tasks />);
		expect(await screen.findByText("the deep reason")).toBeTruthy();
	});

	it("in archive mode fetches /imports/archive and shows a back link", async () => {
		const fetchMock = mockApi([
			item({ id: 1, name: "Old", state: "imported" }),
		]);
		render(<Tasks archive />);
		await screen.findByText("Old");
		expect(fetchMock.mock.calls[0][0]).toBe("/imports/archive");
		expect(screen.getByRole("button", { name: /Back to tasks/ })).toBeTruthy();
		// no status grouping in the flat archive
		expect(screen.queryByText("In progress")).toBeNull();
	});
});

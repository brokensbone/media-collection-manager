import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Imports } from "./Imports";

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

// A detected row awaiting an Import/Discard decision — all the Import view ever shows now.
function item(over: Record<string, unknown> = {}) {
	return {
		id: 1,
		source: "watchdir",
		name: "Album.zip",
		media_kind: "music",
		import_target: "beets",
		classification_detail: null,
		destination_path: null,
		state: "detected",
		matched_album_id: null,
		matched: null,
		matched_owned: false,
		missing: false,
		error_detail: null,
		updated_at: null,
		created_at: "2026-07-29T10:00:00Z",
		...over,
	};
}

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
});

describe("Imports", () => {
	it("shows the source, matched want, a no-match label and destination", async () => {
		mockApi([
			item({
				id: 1,
				source: "transmission",
				name: "Burial-Untrue",
				matched: "Burial — Untrue",
			}),
			item({
				id: 2,
				name: "Mystery",
				import_target: "film",
				media_kind: "film",
				destination_path: "/film/Mystery",
			}),
		]);
		render(<Imports />);
		expect(await screen.findByText("Burial — Untrue")).toBeTruthy();
		expect(screen.getByText("transmission")).toBeTruthy();
		expect(screen.getByText("no match")).toBeTruthy();
		expect(screen.getByText("/film/Mystery")).toBeTruthy();
	});

	it("removes a row from the worklist when Import is clicked (it becomes a task)", async () => {
		const fetchMock = mockApi([item({ id: 9, name: "Only" })]);
		render(<Imports />);
		await screen.findByText("Only");
		fireEvent.click(screen.getByRole("button", { name: "Import" }));

		const posted = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
		expect(posted?.[0]).toBe("/imports/9/import");
		await waitFor(() => expect(screen.queryByText("Only")).toBeNull());
	});

	it("discards a detected row via DELETE and drops it from the list", async () => {
		const fetchMock = mockApi([item({ id: 7, name: "Unwanted" })]);
		render(<Imports />);
		await screen.findByText("Unwanted");
		fireEvent.click(screen.getByRole("button", { name: "Discard" }));

		const deleted = fetchMock.mock.calls.find((c) => c[1]?.method === "DELETE");
		expect(deleted?.[0]).toBe("/imports/7");
		expect(screen.queryByText("Unwanted")).toBeNull();
	});

	it("shows review-only rows with no Import action, just Discard", async () => {
		mockApi([
			item({
				id: 10,
				name: "Mystery Pack",
				media_kind: "unknown",
				import_target: "review",
				classification_detail:
					"Video files found, but the title or type is ambiguous.",
			}),
		]);
		render(<Imports />);
		expect(await screen.findByText("needs review")).toBeTruthy();
		expect(screen.queryByRole("button", { name: "Import" })).toBeNull();
		expect(screen.getByRole("button", { name: "Discard" })).toBeTruthy();
	});

	it("reclassifies a row to workspace", async () => {
		const fetchMock = mockApi([
			item({ id: 12, name: "Mystery Pack", import_target: "review" }),
		]);
		render(<Imports />);
		await screen.findByText("Mystery Pack");
		fireEvent.change(
			screen.getByRole("combobox", { name: "Classify Mystery Pack" }),
			{
				target: { value: "workspace" },
			},
		);

		const posted = fetchMock.mock.calls.find(
			(c) => c[0] === "/imports/12/classify",
		);
		expect(posted?.[1]?.method).toBe("POST");
		expect(posted?.[1]?.body).toBe(JSON.stringify({ kind: "workspace" }));
	});

	it("flags a match that is already owned", async () => {
		mockApi([
			item({
				id: 5,
				name: "Dup",
				matched: "Burial — Untrue",
				matched_owned: true,
			}),
			item({
				id: 6,
				name: "New",
				matched: "Someone — Thing",
				matched_owned: false,
			}),
		]);
		render(<Imports />);
		expect(await screen.findByText("owned")).toBeTruthy();
		expect(screen.getAllByText("owned")).toHaveLength(1);
	});

	it("scans the watch folder and refreshes", async () => {
		const fetchMock = mockApi([]);
		render(<Imports />);
		expect(await screen.findByText("Nothing waiting to import.")).toBeTruthy();
		fireEvent.click(screen.getByRole("button", { name: "Scan watch folder" }));
		const posted = fetchMock.mock.calls.find((c) => c[0] === "/imports/scan");
		expect(posted?.[1]?.method).toBe("POST");
	});

	it("filters the worklist by type and back to all", async () => {
		mockApi([
			item({ id: 1, name: "A Song" }),
			item({
				id: 2,
				name: "The Show S01",
				import_target: "tv",
				media_kind: "tv",
			}),
			item({
				id: 3,
				name: "A Film",
				import_target: "film",
				media_kind: "film",
			}),
		]);
		render(<Imports />);
		await screen.findByText("A Song");
		fireEvent.click(screen.getByRole("button", { name: /\bTV$/ }));
		await waitFor(() => expect(screen.queryByText("A Song")).toBeNull());
		expect(screen.getByText("The Show S01")).toBeTruthy();
		fireEvent.click(screen.getByRole("button", { name: /\ball$/ }));
		await waitFor(() => expect(screen.getByText("A Song")).toBeTruthy());
	});

	it("groups a review-target row under Review, not its media kind", async () => {
		mockApi([
			item({
				id: 1,
				name: "Clean Film",
				import_target: "film",
				media_kind: "film",
			}),
			item({
				id: 2,
				name: "Mixed Pack",
				import_target: "review",
				media_kind: "tv",
			}),
		]);
		render(<Imports />);
		await screen.findByText("Clean Film");
		fireEvent.click(screen.getByRole("button", { name: /\bReview$/ }));
		await waitFor(() => expect(screen.queryByText("Clean Film")).toBeNull());
		expect(screen.getByText("Mixed Pack")).toBeTruthy();
	});

	it("partitions rows into discovery-day groups, newest day first", async () => {
		mockApi([
			item({ id: 1, name: "Older Drop", created_at: "2026-07-27T09:00:00Z" }),
			item({ id: 2, name: "Newer Drop", created_at: "2026-07-29T09:00:00Z" }),
		]);
		render(<Imports />);
		await screen.findByText("Newer Drop");
		// two day-group headings, and the newer day's rows come first in document order
		expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(2);
		const body = document.body.textContent ?? "";
		expect(body.indexOf("Newer Drop")).toBeLessThan(body.indexOf("Older Drop"));
	});

	it("shows no type filter when only one type is present", async () => {
		mockApi([
			item({ id: 1, name: "A Song" }),
			item({ id: 2, name: "Another Song" }),
		]);
		render(<Imports />);
		await screen.findByText("A Song");
		expect(screen.queryByRole("button", { name: /Music$/ })).toBeNull();
	});
});

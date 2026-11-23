import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Decide } from "./Decide";

function mockApi(items: unknown) {
	const fetchMock = vi.fn((_url: string, opts?: { method?: string }) =>
		opts?.method === "POST"
			? Promise.resolve({ ok: true })
			: Promise.resolve({
					json: () =>
						Promise.resolve(
							Array.isArray(items)
								? items.map((item) => ({
										release_year: new Date().getFullYear(),
										...item,
									}))
								: items,
						),
				}),
	);
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	window.history.replaceState(null, "", "/");
});

describe("Decide", () => {
	it("defaults to this year's releases, keeps the backlog accessible and applies hotkeys to the shown rows", async () => {
		const year = new Date().getFullYear();
		const fetchMock = mockApi([
			{ id: 1, artist: "A", title: "Old", reason: "", release_year: year - 1 },
			{ id: 2, artist: "B", title: "New", reason: "", release_year: year },
			{ id: 3, artist: "C", title: "Unknown", reason: "", release_year: null },
		]);
		render(<Decide />);
		await screen.findByText("New");
		expect(screen.queryByText("Old")).toBeNull();
		expect(screen.queryByText("Unknown")).toBeNull();
		fireEvent.keyDown(document.body, { key: "y" });
		await waitFor(() =>
			expect(fetchMock).toHaveBeenCalledWith("/albums/2/keep", {
				method: "POST",
			}),
		);
		fireEvent.click(screen.getByRole("button", { name: /All albums/ }));
		expect(screen.getByText("Old")).toBeTruthy();
		expect(screen.getByText("Unknown")).toBeTruthy();
	});
	it("lists items with their reason", async () => {
		mockApi([
			{ id: 1, artist: "A", title: "T1", reason: "30d", has_art: false },
		]);
		render(<Decide />);
		expect(await screen.findByText("T1")).toBeTruthy();
		expect(screen.getByText("30d")).toBeTruthy();
	});

	it("shows the album_type as a badge", async () => {
		mockApi([
			{
				id: 1,
				artist: "A",
				title: "T1",
				reason: "30d",
				has_art: false,
				album_type: "compilation",
			},
		]);
		render(<Decide />);
		await screen.findByText("T1");
		expect(screen.getByText("compilation")).toBeTruthy();
	});

	it("keeps an item: POSTs and removes it from the queue", async () => {
		const fetchMock = mockApi([
			{ id: 7, artist: "A", title: "Only", reason: "r", has_art: false },
		]);
		render(<Decide />);
		await screen.findByText("Only");
		fireEvent.click(screen.getByRole("button", { name: "Keep" }));
		await screen.findByText(/Nothing to judge/);
		const posted = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
		expect(posted?.[0]).toBe("/albums/7/keep");
	});

	it("notifies onChange after an action so the dashboard can refresh", async () => {
		mockApi([
			{ id: 7, artist: "A", title: "Only", reason: "r", has_art: false },
		]);
		const onChange = vi.fn();
		render(<Decide onChange={onChange} />);
		await screen.findByText("Only");
		fireEvent.click(screen.getByRole("button", { name: "Drop" }));
		await waitFor(() => expect(onChange).toHaveBeenCalled());
	});

	it("ignores triage hotkeys while a text field is focused", async () => {
		const fetchMock = mockApi([
			{ id: 7, artist: "A", title: "Only", reason: "r", has_art: false },
		]);
		render(<Decide />);
		await screen.findByText("Only");
		const input = document.createElement("input");
		document.body.appendChild(input);
		fireEvent.keyDown(input, { key: "s" }); // typing 's' in a field must not snooze
		expect(fetchMock.mock.calls.some((c) => c[1]?.method === "POST")).toBe(
			false,
		);
		input.remove();
	});

	it("keeps the scope in the URL", async () => {
		const year = new Date().getFullYear();
		mockApi([
			{ id: 1, artist: "A", title: "Old", reason: "", release_year: year - 1 },
		]);
		window.history.replaceState(null, "", "/#decide?scope=all");
		render(<Decide />);
		expect(await screen.findByText("Old")).toBeTruthy();
		const all = screen.getByRole("button", { name: /^All albums/ });
		expect(all.getAttribute("aria-pressed")).toBe("true");
		fireEvent.click(screen.getByRole("button", { name: /^This year/ }));
		expect(window.location.hash).toBe("#decide");
		fireEvent.click(all);
		expect(window.location.hash).toBe("#decide?scope=all");
	});

	it("explains an empty year only without a query; with one, shows no matches", async () => {
		const year = new Date().getFullYear();
		mockApi([
			{ id: 1, artist: "A", title: "Old", reason: "", release_year: year - 1 },
		]);
		const { rerender } = render(<Decide />);
		expect(await screen.findByText("No albums match this view.")).toBeTruthy();
		rerender(<Decide query="zzz" />);
		expect(screen.getByText("No matches for “zzz”")).toBeTruthy();
		expect(screen.queryByText("No albums match this view.")).toBeNull();
	});

	it("marks the selected row and shows key hints only in it", async () => {
		mockApi([
			{ id: 1, artist: "A", title: "First", reason: "" },
			{ id: 2, artist: "B", title: "Second", reason: "" },
		]);
		render(<Decide />);
		await screen.findByText("First");
		const first = screen.getByText("First").closest("tr");
		expect(first?.getAttribute("aria-selected")).toBe("true");
		expect(first?.className).toBe("sel");
		fireEvent.keyDown(document.body, { key: "ArrowDown" });
		expect(first?.hasAttribute("aria-selected")).toBe(false);
		expect(
			screen.getByText("Second").closest("tr")?.getAttribute("aria-selected"),
		).toBe("true");
		expect(screen.getAllByRole("button", { name: "Keep" })).toHaveLength(2);
	});

	it("with a limit: no scope control, no keyboard, no selection", async () => {
		const year = new Date().getFullYear();
		const fetchMock = mockApi([
			{ id: 1, artist: "A", title: "Old", reason: "", release_year: year - 1 },
		]);
		render(<Decide limit={5} />);
		expect(await screen.findByText("Old")).toBeTruthy();
		expect(screen.queryByRole("button", { name: /All albums/ })).toBeNull();
		expect(document.querySelector("[aria-selected]")).toBeNull();
		fireEvent.keyDown(document.body, { key: "y" });
		expect(fetchMock.mock.calls.some((c) => c[1]?.method === "POST")).toBe(
			false,
		);
	});

	it("shows an error with Retry when the load fails", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn(() => Promise.resolve({ ok: false, status: 500 })),
		);
		render(<Decide />);
		expect(await screen.findByRole("alert")).toBeTruthy();
		expect(screen.getByText("Couldn’t load albums to judge.")).toBeTruthy();
		expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
		expect(screen.queryByText(/Nothing to judge/)).toBeNull();
	});
});

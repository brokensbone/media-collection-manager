import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Releases } from "./Releases";

function mockApi(items: unknown) {
	const fetchMock = vi.fn((_url: string, opts?: { method?: string }) =>
		opts?.method === "POST"
			? Promise.resolve({ ok: true })
			: Promise.resolve({ json: () => Promise.resolve(items) }),
	);
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	window.history.replaceState(null, "", "/");
});

describe("Releases", () => {
	it("lists suggested releases", async () => {
		mockApi([{ id: 1, artist: "The Band", title: "New One", has_art: false }]);
		render(<Releases />);
		expect(await screen.findByText("New One")).toBeTruthy();
	});

	it("links the cover to the album on Spotify in a new tab", async () => {
		mockApi([
			{
				id: 1,
				artist: "The Band",
				title: "New One",
				has_art: true,
				spotify_id: "spot9",
			},
		]);
		const { container } = render(<Releases />);
		await screen.findByText("New One");
		const link = container.querySelector("a") as HTMLAnchorElement;
		expect(link.href).toContain("open.spotify.com/album/spot9");
		expect(link.target).toBe("_blank");
	});

	it("shows the album_type as a badge, and nothing when null", async () => {
		mockApi([
			{
				id: 1,
				artist: "A",
				title: "Single One",
				has_art: false,
				album_type: "single",
			},
			{
				id: 2,
				artist: "B",
				title: "No Type",
				has_art: false,
				album_type: null,
			},
		]);
		render(<Releases />);
		await screen.findByText("Single One");
		expect(screen.getByText("single")).toBeTruthy();
		expect(screen.queryByText("album")).toBeNull();
	});

	it("want: POSTs and removes the row", async () => {
		const fetchMock = mockApi([
			{ id: 5, artist: "B", title: "Only", has_art: false },
		]);
		render(<Releases />);
		await screen.findByText("Only");
		fireEvent.click(screen.getByRole("button", { name: "Want" }));
		await screen.findByText(/No new releases/);
		const posted = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
		expect(posted?.[0]).toBe("/albums/5/want");
	});

	it("shows an error with Retry when the load fails, not the empty sentence", async () => {
		const fetchMock = vi.fn(() => Promise.reject(new Error("down")));
		vi.stubGlobal("fetch", fetchMock);
		render(<Releases />);
		expect(await screen.findByText("Couldn’t load releases.")).toBeTruthy();
		expect(screen.queryByText(/No new releases/)).toBeNull();
		mockApi([{ id: 1, artist: "B", title: "Back", has_art: false }]);
		fireEvent.click(screen.getByRole("button", { name: "Retry" }));
		expect(await screen.findByText("Back")).toBeTruthy();
	});

	it("shows the no-match state when the filter leaves nothing", async () => {
		mockApi([{ id: 1, artist: "B", title: "Only", has_art: false }]);
		render(<Releases query="zzz" />);
		expect(await screen.findByText("No matches for “zzz”")).toBeTruthy();
		expect(screen.getByRole("button", { name: "Clear filter" })).toBeTruthy();
	});

	it("moves with j and saves, wants or dismisses the selected row by key", async () => {
		const fetchMock = mockApi([
			{ id: 1, artist: "A", title: "First", has_art: false },
			{ id: 2, artist: "B", title: "Second", has_art: false },
			{ id: 3, artist: "C", title: "Third", has_art: false },
		]);
		render(<Releases />);
		await screen.findByText("First");
		expect(
			screen.getByText("First").closest("tr")?.getAttribute("aria-selected"),
		).toBe("true");
		fireEvent.keyDown(document.body, { key: "j" });
		expect(
			screen.getByText("Second").closest("tr")?.getAttribute("aria-selected"),
		).toBe("true");
		fireEvent.keyDown(document.body, { key: "w" });
		await waitFor(() =>
			expect(fetchMock).toHaveBeenCalledWith("/albums/2/want", {
				method: "POST",
			}),
		);
		fireEvent.keyDown(document.body, { key: "d" });
		await waitFor(() =>
			expect(fetchMock).toHaveBeenCalledWith("/albums/3/dismiss", {
				method: "POST",
			}),
		);
		fireEvent.keyDown(document.body, { key: "s" });
		await waitFor(() =>
			expect(fetchMock).toHaveBeenCalledWith("/albums/1/save", {
				method: "POST",
			}),
		);
	});

	it("with a limit: no header, no keyboard, no selection", async () => {
		const fetchMock = mockApi([
			{ id: 1, artist: "A", title: "First", has_art: false },
		]);
		render(<Releases limit={5} />);
		await screen.findByText("First");
		expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
		expect(document.querySelector("thead")).toBeNull();
		expect(document.querySelector("[aria-selected]")).toBeNull();
		fireEvent.keyDown(document.body, { key: "s" });
		expect(fetchMock.mock.calls.some((c) => c[1]?.method === "POST")).toBe(
			false,
		);
	});
});

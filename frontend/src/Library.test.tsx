import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Library } from "./Library";

function mockAlbums(body: unknown) {
	vi.stubGlobal(
		"fetch",
		vi.fn(() => Promise.resolve({ json: () => Promise.resolve(body) })),
	);
}

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
});

describe("Library", () => {
	it("lists albums with ownership", async () => {
		mockAlbums([
			{ id: 1, artist: "A", title: "Owned Album", state: "owned", owned: true },
			{
				id: 2,
				artist: "B",
				title: "Saved Album",
				state: "saved",
				owned: false,
			},
		]);
		const { container } = render(<Library />);
		await screen.findByText("Owned Album");
		expect(container.textContent).toContain("Saved Album");
		expect(container.textContent).toContain("owned");
		expect(container.textContent).toContain("saved");
	});

	it("shows an empty state", async () => {
		mockAlbums([]);
		render(<Library />);
		expect(await screen.findByText(/Nothing here/)).toBeTruthy();
	});

	it("titles the dismissed view and shows its count", async () => {
		mockAlbums([
			{ id: 1, artist: "A", title: "Gone", state: "dismissed", owned: false },
		]);
		render(<Library state="dismissed" />);
		expect(
			await screen.findByRole("heading", { level: 1, name: "Dismissed" }),
		).toBeTruthy();
		expect(screen.getByText("Gone")).toBeTruthy();
		expect(screen.queryByText("dismissed")).toBeNull(); // state column only in mixed lists
	});

	it("shows an error state with Retry when the load fails", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn(() => Promise.reject(new Error("down"))),
		);
		render(<Library state="dismissed" />);
		expect(await screen.findByText(/Couldn’t load dismissed/)).toBeTruthy();
		expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
	});
});

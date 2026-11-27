import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AutofileModal, type AutofileRun } from "./AutofileModal";

const album = { beets_id: "new", artist: "Ghost Dubs", title: "Oblique" };
const suggestion: AutofileRun = {
	id: 12,
	status: "suggested",
	model: "jev-1.14.0",
	error: null,
	evidence: {
		sources: [
			{
				url: "https://ghostdubs.bandcamp.com/album/oblique",
				description: "Deep dub",
				tags: ["dub"],
			},
		],
	},
	result: {
		destination: "Collection / Reggae & Dub / Dub",
		destination_count: 24,
		capacity: 50,
		steps: [
			{
				node_id: 1,
				node: "Collection",
				choice: "Reggae & Dub [2]",
				probability: 0.85,
				alternatives: [
					{ choice: "Reggae & Dub [2]", probability: 0.85 },
					{ choice: "Electronic [6]", probability: 0.1 },
				],
			},
		],
	},
};
const response = (data: unknown) => ({ ok: true, json: async () => data });
afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
});

describe("Autofile modal", () => {
	it("opens loading, issues one request under StrictMode, and accepts only on click", async () => {
		let finish!: (value: unknown) => void;
		const pending = new Promise((resolve) => {
			finish = resolve;
		});
		const fetch = vi
			.fn()
			.mockReturnValueOnce(pending)
			.mockResolvedValue(response({ status: "accepted" }));
		vi.stubGlobal("fetch", fetch);
		const onClose = vi.fn();
		const onAccepted = vi.fn();
		render(
			<StrictMode>
				<AutofileModal
					album={album}
					onClose={onClose}
					onAccepted={onAccepted}
				/>
			</StrictMode>,
		);
		expect(screen.getByRole("status").textContent).toContain("Finding a crate");
		expect(fetch).toHaveBeenCalledTimes(1);
		finish(response(suggestion));
		await screen.findByText("Collection / Reggae & Dub / Dub");
		expect(screen.getByText("85%")).toBeTruthy();
		expect(fetch).toHaveBeenCalledTimes(1);
		fireEvent.click(screen.getByRole("button", { name: "File in Dub" }));
		await waitFor(() => expect(onAccepted).toHaveBeenCalledTimes(1));
		expect(fetch.mock.calls[1][0]).toBe("/crates/autofile/12/accept");
		expect(onClose).toHaveBeenCalledTimes(1);
	});
	it("dismisses the saved run without accepting", async () => {
		const fetch = vi
			.fn()
			.mockResolvedValueOnce(response(suggestion))
			.mockResolvedValue(response({ status: "dismissed" }));
		vi.stubGlobal("fetch", fetch);
		const onAccepted = vi.fn();
		const onClose = vi.fn();
		render(
			<AutofileModal album={album} onClose={onClose} onAccepted={onAccepted} />,
		);
		await screen.findByText("Saved result #12 · jev-1.14.0");
		fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
		await waitFor(() => expect(onClose).toHaveBeenCalled());
		expect(fetch.mock.calls[1][0]).toBe("/crates/autofile/12/dismiss");
		expect(onAccepted).not.toHaveBeenCalled();
	});
	it("shows stale-state rejection and keeps the suggestion open", async () => {
		vi.stubGlobal(
			"fetch",
			vi
				.fn()
				.mockResolvedValueOnce(response(suggestion))
				.mockResolvedValue({
					ok: false,
					json: async () => ({
						detail: "The album moved. Run Autofile again.",
					}),
				}),
		);
		const onClose = vi.fn();
		render(
			<AutofileModal album={album} onClose={onClose} onAccepted={vi.fn()} />,
		);
		await screen.findByText("85%");
		fireEvent.click(screen.getByRole("button", { name: "File in Dub" }));
		expect((await screen.findByRole("alert")).textContent).toContain(
			"The album moved",
		);
		expect(onClose).not.toHaveBeenCalled();
	});

	it("offers only dismissal when the route has no destination", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				response({
					...suggestion,
					status: "review",
					result: {
						steps: [],
						reason: "No suitable child crate was found.",
						needs_review: true,
					},
				}),
			),
		);
		render(
			<AutofileModal album={album} onClose={vi.fn()} onAccepted={vi.fn()} />,
		);
		await screen.findByText("No destination suggested.");
		expect(
			screen.getByText(/The album will stay in its current crate/),
		).toBeTruthy();
		expect(
			screen.queryByRole("button", { name: /File in|Accept move/ }),
		).toBeNull();
		expect(screen.queryByText(/Low-confidence suggestion/)).toBeNull();
		expect(screen.getByRole("button", { name: "Dismiss" })).toBeTruthy();
	});
	it("does not offer filing into a destination blocked for review", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				response({
					...suggestion,
					status: "review",
					result: {
						...suggestion.result,
						reason: "The suggested crate is full.",
					},
				}),
			),
		);
		render(
			<AutofileModal album={album} onClose={vi.fn()} onAccepted={vi.fn()} />,
		);
		await screen.findByText("The suggested crate is full.");
		expect(
			screen.queryByRole("button", { name: /File in|Accept move/ }),
		).toBeNull();
	});

	it("lets the user accept an uncertain suggestion after inspecting alternatives", async () => {
		const fetch = vi
			.fn()
			.mockResolvedValueOnce(
				response({
					...suggestion,
					result: { ...suggestion.result, needs_review: true },
				}),
			)
			.mockResolvedValue(response({ status: "accepted" }));
		vi.stubGlobal("fetch", fetch);
		const onAccepted = vi.fn();
		render(
			<AutofileModal album={album} onClose={vi.fn()} onAccepted={onAccepted} />,
		);
		await screen.findByText(/Low-confidence suggestion/);
		fireEvent.click(screen.getByText("Show alternatives"));
		expect(screen.getByText("Electronic: 10%")).toBeTruthy();
		const accept = screen.getByRole("button", {
			name: "File in Dub",
		}) as HTMLButtonElement;
		expect(accept.disabled).toBe(false);
		fireEvent.click(accept);
		await waitFor(() => expect(onAccepted).toHaveBeenCalledOnce());
	});
});

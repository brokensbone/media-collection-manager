import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Crates } from "./Crates";

function mockCrates(box: unknown) {
	const fetchMock = vi.fn(
		(_url: string, opts?: { method?: string; body?: string }) =>
			opts?.method
				? Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
				: Promise.resolve({ json: () => Promise.resolve(box) }),
	);
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

function boxView(over: Record<string, unknown> = {}) {
	return {
		id: 1,
		name: "Collection",
		parent_id: null,
		breadcrumb: [{ id: 1, name: "Collection" }],
		children: [{ id: 2, name: "Electronic", loose_count: 3, total_count: 12 }],
		records: [
			{
				beets_id: "b1",
				artist: "Burial",
				title: "Untrue",
				year: 2007,
				media: "CD",
			},
		],
		loose_count: 1,
		total_count: 13,
		soft_cap: 50,
		over_cap: false,
		...over,
	};
}

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	window.location.hash = "";
});

describe("Crates", () => {
	it("shows the box, its sub-boxes with counts, and loose records", async () => {
		mockCrates(boxView());
		render(<Crates />);
		expect(await screen.findByRole("heading", { name: "Crates" })).toBeTruthy();
		expect(screen.getByText("Electronic")).toBeTruthy();
		expect(screen.getByText("12")).toBeTruthy(); // sub-box total count
		expect(screen.getByText("Burial")).toBeTruthy();
		expect(screen.getByText("Untrue")).toBeTruthy();
	});

	it("reveals move actions when a record is selected; root cannot kick up", async () => {
		mockCrates(boxView());
		render(<Crates />);
		await screen.findByText("Burial");
		fireEvent.click(screen.getByLabelText("Select Burial — Untrue"));
		expect(screen.getByText("1 selected")).toBeTruthy();
		const kick = screen.getByRole("button", {
			name: "Kick up",
		}) as HTMLButtonElement;
		expect(kick.disabled).toBe(true); // root has no parent
	});

	it("selects a range with shift-click and toggles the cursor row with space", async () => {
		const records = ["A", "B", "C", "D"].map((t, i) => ({
			beets_id: `b${i}`,
			artist: `Artist ${t}`,
			title: t,
			year: null,
			media: null,
		}));
		mockCrates(boxView({ records }));
		render(<Crates />);
		await screen.findByText("Artist A");
		fireEvent.click(screen.getByLabelText("Select Artist B — B"));
		fireEvent.click(screen.getByLabelText("Select Artist D — D"), {
			shiftKey: true,
		});
		expect(screen.getByText("3 selected")).toBeTruthy();
		fireEvent.keyDown(document.body, { key: " " });
		expect(screen.getByText("4 selected")).toBeTruthy();
	});

	it("creates a sub-box via POST /crates/box under the current box", async () => {
		const fetchMock = mockCrates(boxView());
		render(<Crates />);
		await screen.findByRole("heading", { name: "Crates" });
		fireEvent.change(screen.getByPlaceholderText("new sub-box…"), {
			target: { value: "Jazz" },
		});
		fireEvent.click(screen.getByRole("button", { name: "Add" }));
		await waitFor(() => {
			const posted = fetchMock.mock.calls.find(
				(c) => c[0] === "/crates/box" && c[1]?.method === "POST",
			);
			expect(posted).toBeTruthy();
			expect(String(posted?.[1]?.body)).toContain("Jazz");
		});
	});

	it("shows a cap-meter over-cap nudge when the loose pile exceeds the soft cap", async () => {
		mockCrates(boxView({ loose_count: 60, soft_cap: 50, over_cap: true }));
		render(<Crates />);
		expect(await screen.findByText(/consider splitting/)).toBeTruthy();
	});

	it("previews split suggestions and applies the chosen one", async () => {
		const suggestions = [
			{
				key: "decade",
				label: "Decade",
				groups: [
					{ name: "2000s", count: 24 },
					{ name: "2010s", count: 21 },
				],
				covers: 45,
				leaves: 12,
			},
		];
		const fetchMock = vi.fn(
			(url: string, opts?: { method?: string; body?: string }) => {
				if (opts?.method)
					return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
				const body = url.endsWith("/split-suggestions")
					? suggestions
					: boxView();
				return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
			},
		);
		vi.stubGlobal("fetch", fetchMock);

		render(<Crates />);
		await screen.findByRole("heading", { name: "Crates" });
		fireEvent.click(screen.getByRole("button", { name: "Suggest a split" }));

		expect(await screen.findByText(/2000s \(24\)/)).toBeTruthy();
		expect(screen.getByText(/leaves 12/)).toBeTruthy();

		fireEvent.click(screen.getByRole("button", { name: "Apply" }));
		await waitFor(() => {
			const posted = fetchMock.mock.calls.find(
				(c) => c[0] === "/crates/box/1/split" && c[1]?.method === "POST",
			);
			expect(posted).toBeTruthy();
			expect(String(posted?.[1]?.body)).toContain("decade");
		});
	});

	it("reports when no clean split is found", async () => {
		const fetchMock = vi.fn((url: string, opts?: { method?: string }) => {
			if (opts?.method)
				return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
			const body = url.endsWith("/split-suggestions") ? [] : boxView();
			return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
		});
		vi.stubGlobal("fetch", fetchMock);

		render(<Crates />);
		await screen.findByRole("heading", { name: "Crates" });
		fireEvent.click(screen.getByRole("button", { name: "Suggest a split" }));
		expect(
			await screen.findByText("No clean split found — file by hand."),
		).toBeTruthy();
	});

	it("shows an error state with Retry instead of loading forever", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn(() => Promise.resolve({ ok: false, status: 500 })),
		);
		render(<Crates />);
		expect(await screen.findByText(/Couldn’t load this crate/)).toBeTruthy();
		expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
	});

	it("labels the capacity meter", async () => {
		mockCrates(boxView());
		render(<Crates />);
		const meter = await screen.findByRole("meter", { name: "Loose records" });
		expect(meter.getAttribute("aria-valuenow")).toBe("1");
		expect(meter.getAttribute("aria-valuemax")).toBe("50");
	});

	it("links sub-boxes and shows the breadcrumb only below the root", async () => {
		mockCrates(
			boxView({
				id: 2,
				name: "Electronic",
				parent_id: 1,
				breadcrumb: [
					{ id: 1, name: "Collection" },
					{ id: 2, name: "Electronic" },
				],
				children: [{ id: 3, name: "Ambient", loose_count: 1, total_count: 6 }],
			}),
		);
		render(<Crates />);
		expect(
			await screen.findByRole("heading", { level: 1, name: "Electronic" }),
		).toBeTruthy();
		expect(
			screen.getByRole("link", { name: "Crates" }).getAttribute("href"),
		).toBe("#crates");
		expect(
			screen.getByRole("link", { name: /Ambient/ }).getAttribute("href"),
		).toBe("#crates?box=3");
	});

	it("toggles a record by clicking its row, and selects all with the header box", async () => {
		mockCrates(
			boxView({
				records: [
					{
						beets_id: "b1",
						artist: "Burial",
						title: "Untrue",
						year: 2007,
						media: "CD",
					},
					{
						beets_id: "b2",
						artist: "Four Tet",
						title: "Rounds",
						year: 2003,
						media: "CD",
					},
				],
			}),
		);
		render(<Crates />);
		fireEvent.click(await screen.findByText("Rounds"));
		expect(screen.getByText("1 selected")).toBeTruthy();
		fireEvent.click(screen.getByLabelText("Select all loose records"));
		expect(screen.getByText("2 selected")).toBeTruthy();
		fireEvent.click(screen.getByLabelText("Select all loose records"));
		expect(screen.queryByText(/selected$/)).toBeNull();
	});

	it("filters the loose records with ?q= and keeps the box", async () => {
		window.location.hash = "#crates?box=1&q=four";
		mockCrates(
			boxView({
				records: [
					{
						beets_id: "b1",
						artist: "Burial",
						title: "Untrue",
						year: 2007,
						media: "CD",
					},
					{
						beets_id: "b2",
						artist: "Four Tet",
						title: "Rounds",
						year: 2003,
						media: "CD",
					},
				],
			}),
		);
		render(<Crates />);
		expect(await screen.findByText("Rounds")).toBeTruthy();
		expect(screen.queryByText("Burial")).toBeNull();
	});
});

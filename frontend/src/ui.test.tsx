import {
	act,
	cleanup,
	fireEvent,
	render,
	renderHook,
	screen,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
	Badge,
	EmptyState,
	ErrorState,
	FilterBox,
	GroupHead,
	IMPORT_STATE_TONE,
	Kbd,
	ListHints,
	LiveRegion,
	Loading,
	NoMatches,
	PageHeader,
	PollWarning,
	Segmented,
	SegmentedLinks,
	StatusBadge,
	useAnnounceCount,
} from "./ui";

afterEach(() => {
	cleanup();
	window.location.hash = "";
});

describe("PageHeader", () => {
	it("renders one h1 named by the title, with the count beside it", () => {
		render(
			<PageHeader
				title="Owned"
				count="12 of 89"
				back={{ href: "#tasks", label: "Tasks" }}
			>
				<button type="button">Scan</button>
			</PageHeader>,
		);
		expect(
			screen.getByRole("heading", { level: 1, name: "Owned" }),
		).toBeTruthy();
		expect(screen.getByText("12 of 89")).toBeTruthy();
		expect(screen.getByRole("button", { name: "Scan" })).toBeTruthy();
		expect(
			screen.getByRole("link", { name: /Tasks/ }).getAttribute("href"),
		).toBe("#tasks");
	});
});

describe("GroupHead", () => {
	it("keeps the title as the heading's own text, count as a sibling", () => {
		render(<GroupHead title="Failed" count={4} tone="danger" />);
		const h = screen.getByRole("heading", { level: 2, name: "Failed" });
		expect(screen.getByText("Failed")).toBe(h);
		expect(screen.getByText("4").className).toContain("tone-danger");
	});
});

describe("FilterBox", () => {
	it("binds to ?q= and clears on Escape", () => {
		window.location.hash = "owned?sort=title";
		render(<FilterBox />);
		const input = screen.getByRole("searchbox", {
			name: "Filter",
		}) as HTMLInputElement;
		expect(input.placeholder).toMatch(/filter/i);
		fireEvent.change(input, { target: { value: "bur" } });
		expect(window.location.hash).toBe("#owned?sort=title&q=bur");
		expect(input.value).toBe("bur");
		fireEvent.keyDown(input, { key: "Escape" });
		expect(window.location.hash).toBe("#owned?sort=title");
		expect(input.value).toBe("");
	});
});

describe("Segmented", () => {
	it("marks the chosen option with aria-pressed, label first then count", () => {
		const onChange = vi.fn();
		render(
			<Segmented
				ariaLabel="Kind"
				value="all"
				onChange={onChange}
				options={[
					{ value: "all", label: "All", count: 15 },
					{ value: "tv", label: "TV", count: 3 },
				]}
			/>,
		);
		expect(screen.getByRole("group", { name: "Kind" })).toBeTruthy();
		const all = screen.getByRole("button", { name: /^All\b/ });
		const tv = screen.getByRole("button", { name: /^TV\b/ });
		expect(all.getAttribute("aria-pressed")).toBe("true");
		expect(tv.getAttribute("aria-pressed")).toBe("false");
		expect(tv.textContent).toBe("TV 3");
		fireEvent.click(tv);
		expect(onChange).toHaveBeenCalledWith("tv");
	});

	it("has a link variant that marks the current item", () => {
		const onSelect = vi.fn();
		render(
			<SegmentedLinks
				ariaLabel="Programmes"
				current="b"
				ariaCurrent="date"
				onSelect={onSelect}
				items={[
					{ key: "a", href: "#radio/a", label: "Mon 21 Sep" },
					{ key: "b", href: "#radio/b", label: "Tue 22 Sep" },
				]}
			/>,
		);
		expect(
			screen
				.getByRole("link", { name: "Tue 22 Sep" })
				.getAttribute("aria-current"),
		).toBe("date");
		expect(
			screen
				.getByRole("link", { name: "Mon 21 Sep" })
				.getAttribute("aria-current"),
		).toBeNull();
		fireEvent.click(screen.getByRole("link", { name: "Mon 21 Sep" }));
		expect(onSelect).toHaveBeenCalledWith("a");
	});
});

describe("badges", () => {
	it("StatusBadge shows its label as its own text, in the tone", () => {
		render(
			<StatusBadge tone={IMPORT_STATE_TONE.importing} pulse>
				importing…
			</StatusBadge>,
		);
		const el = screen.getByText("importing…");
		expect(el.className).toBe("status status-info pulse");
	});

	it("maps import states to tones", () => {
		expect(IMPORT_STATE_TONE.failed).toBe("danger");
		expect(IMPORT_STATE_TONE.imported).toBe("ok");
		expect(IMPORT_STATE_TONE.skipped).toBe("muted");
	});

	it("Badge is neutral and Kbd stays out of accessible names", () => {
		render(
			<>
				<Badge title="Album type">single</Badge>
				<button type="button">
					Keep <Kbd>y</Kbd>
				</button>
			</>,
		);
		expect(screen.getByText("single").className).toBe("badge");
		expect(screen.getByRole("button", { name: "Keep" })).toBeTruthy();
	});

	it("ListHints renders each key with its label", () => {
		const { container } = render(
			<ListHints
				items={[
					["j/k", "move"],
					["y", "keep"],
				]}
			/>,
		);
		expect(container.querySelectorAll(".kbd")).toHaveLength(2);
		expect(container.textContent).toBe("j/kmoveykeep");
	});
});

describe("state components", () => {
	it("Loading is a status with hidden text", () => {
		render(<Loading rows={4} />);
		expect(screen.getByRole("status").textContent).toContain("Loading…");
	});

	it("EmptyState shows the title", () => {
		render(<EmptyState title="Nothing to judge." hint="All done." />);
		expect(screen.getByText("Nothing to judge.")).toBeTruthy();
		expect(screen.getByText("All done.")).toBeTruthy();
	});

	it("NoMatches quotes the query and clears the filter", () => {
		window.location.hash = "owned?q=zz";
		render(<NoMatches query="zz" />);
		expect(screen.getByText("No matches for “zz”")).toBeTruthy();
		fireEvent.click(screen.getByRole("button", { name: "Clear filter" }));
		expect(window.location.hash).toBe("#owned");
	});

	it("ErrorState is an alert with Retry", () => {
		const onRetry = vi.fn();
		render(<ErrorState what="releases" onRetry={onRetry} />);
		const alert = screen.getByRole("alert");
		expect(alert.textContent).toContain("Couldn’t load releases.");
		fireEvent.click(screen.getByRole("button", { name: "Retry" }));
		expect(onRetry).toHaveBeenCalled();
	});

	it("PollWarning renders only when shown", () => {
		const { rerender } = render(<PollWarning show={false} />);
		expect(screen.queryByText("Reconnecting…")).toBeNull();
		rerender(<PollWarning show />);
		expect(screen.getByText("Reconnecting…")).toBeTruthy();
	});
});

describe("useAnnounceCount", () => {
	it("announces N of M in the live region while a filter is active", () => {
		const { container } = render(<LiveRegion />);
		const region = container.querySelector("[aria-live]") as HTMLElement;
		const { rerender, unmount } = renderHook(
			({ active }) => useAnnounceCount(12, 89, active),
			{ initialProps: { active: true } },
		);
		expect(region.textContent).toBe("12 of 89 shown");
		rerender({ active: false });
		expect(region.textContent).toBe("");
		act(() => unmount());
	});
});

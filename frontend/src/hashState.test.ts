import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
	parseHash,
	setHashParams,
	setHashPath,
	useHashParam,
	useQuery,
} from "./hashState";

afterEach(() => {
	window.location.hash = "";
});

describe("parseHash", () => {
	it("splits the path from its params", () => {
		const { path, params } = parseHash("#tasks?log=5&q=bur");
		expect(path).toBe("tasks");
		expect(params.get("log")).toBe("5");
		expect(params.get("q")).toBe("bur");
	});

	it("handles a hash with no params, and no hash at all", () => {
		expect(parseHash("#radio/2026-09-22").path).toBe("radio/2026-09-22");
		expect(parseHash("").path).toBe("");
		expect([...parseHash("").params]).toEqual([]);
	});
});

describe("setHashParams", () => {
	it("merges into the existing params and keeps the path", () => {
		window.location.hash = "tasks?q=bur";
		setHashParams({ log: 42 });
		expect(window.location.hash).toBe("#tasks?q=bur&log=42");
	});

	it("removes a key on null or empty, leaving no trailing ?", () => {
		window.location.hash = "tasks?log=5";
		setHashParams({ log: null });
		expect(window.location.hash).toBe("#tasks");
		window.location.hash = "decide?q=x";
		setHashParams({ q: "" });
		expect(window.location.hash).toBe("#decide");
	});

	it("pushes history by default and replaces when asked", () => {
		window.location.hash = "decide";
		const before = window.history.length;
		setHashParams({ scope: "all" });
		expect(window.history.length).toBe(before + 1);
		setHashParams({ q: "b" }, { replace: true });
		expect(window.history.length).toBe(before + 1);
		expect(window.location.hash).toBe("#decide?scope=all&q=b");
	});

	it("dispatches hashchange so listeners update", () => {
		window.location.hash = "owned";
		const onHash = vi.fn();
		window.addEventListener("hashchange", onHash);
		setHashParams({ sort: "title" }, { replace: true });
		window.removeEventListener("hashchange", onHash);
		expect(onHash).toHaveBeenCalledTimes(1);
	});

	it("does nothing when the hash would not change", () => {
		window.location.hash = "owned?sort=title";
		const onHash = vi.fn();
		window.addEventListener("hashchange", onHash);
		setHashParams({ sort: "title" });
		window.removeEventListener("hashchange", onHash);
		expect(onHash).not.toHaveBeenCalled();
	});
});

describe("setHashPath", () => {
	it("drops every param", () => {
		window.location.hash = "decide?q=x&scope=all";
		setHashPath("acquire");
		expect(window.location.hash).toBe("#acquire");
	});
});

describe("useHashParam and useQuery", () => {
	it("read reactively and write through the helper", () => {
		window.location.hash = "import?kind=tv&q=abc";
		const { result } = renderHook(() => ({
			kind: useHashParam("kind"),
			q: useQuery(),
		}));
		expect(result.current.kind[0]).toBe("tv");
		expect(result.current.q).toBe("abc");
		act(() => result.current.kind[1](null));
		expect(result.current.kind[0]).toBeNull();
		expect(result.current.q).toBe("abc");
		expect(window.location.hash).toBe("#import?q=abc");
	});

	it("returns an empty query when q is absent", () => {
		window.location.hash = "decide";
		const { result } = renderHook(() => useQuery());
		expect(result.current).toBe("");
	});
});

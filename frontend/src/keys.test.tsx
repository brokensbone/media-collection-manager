import { act, cleanup, fireEvent, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { isTypingTarget, useRowKeys } from "./keys";

afterEach(cleanup);

describe("useRowKeys", () => {
	it("moves with j/k and arrows, clamped, and runs actions on the selection", () => {
		const keep = vi.fn();
		const { result } = renderHook(() =>
			useRowKeys({ count: 3, actions: { y: keep } }),
		);
		expect(result.current.sel).toBe(0);
		act(() => {
			fireEvent.keyDown(window, { key: "j" });
		});
		act(() => {
			fireEvent.keyDown(window, { key: "ArrowDown" });
		});
		act(() => {
			fireEvent.keyDown(window, { key: "j" });
		});
		expect(result.current.sel).toBe(2);
		act(() => {
			fireEvent.keyDown(window, { key: "k" });
		});
		expect(result.current.sel).toBe(1);
		fireEvent.keyDown(window, { key: "y" });
		expect(keep).toHaveBeenCalledWith(1);
		expect(result.current.rowProps(1)).toMatchObject({
			className: "sel",
			"aria-selected": true,
		});
		expect(result.current.rowProps(0)).toEqual({});
	});

	it("ignores keys when disabled, with modifiers, or while typing", () => {
		const keep = vi.fn();
		const { rerender } = renderHook(
			({ enabled }) => useRowKeys({ count: 2, enabled, actions: { y: keep } }),
			{ initialProps: { enabled: false } },
		);
		fireEvent.keyDown(window, { key: "y" });
		rerender({ enabled: true });
		fireEvent.keyDown(window, { key: "y", ctrlKey: true });
		const input = document.createElement("input");
		document.body.append(input);
		fireEvent.keyDown(input, { key: "y" });
		input.remove();
		expect(keep).not.toHaveBeenCalled();
	});
});

describe("isTypingTarget", () => {
	it("is true for fields and false for buttons", () => {
		expect(isTypingTarget(document.createElement("select"))).toBe(true);
		expect(isTypingTarget(document.createElement("textarea"))).toBe(true);
		expect(isTypingTarget(document.createElement("button"))).toBe(false);
		expect(isTypingTarget(null)).toBe(false);
	});
});

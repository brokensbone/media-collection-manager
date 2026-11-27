import {
	useCallback,
	useEffect,
	useLayoutEffect,
	useRef,
	useState,
} from "react";

export function isTypingTarget(target: EventTarget | null): boolean {
	if (!(target instanceof HTMLElement)) return false;
	const tag = target.tagName;
	return (
		tag === "INPUT" ||
		tag === "TEXTAREA" ||
		tag === "SELECT" ||
		target.isContentEditable === true
	);
}

// True when a global shortcut must not fire for this event.
export function shouldIgnoreKey(e: KeyboardEvent): boolean {
	return (
		e.defaultPrevented ||
		e.metaKey ||
		e.ctrlKey ||
		e.altKey ||
		isTypingTarget(e.target) ||
		document.querySelector("dialog[open]") !== null
	);
}

type RowProps = {
	className?: string;
	"aria-selected"?: true;
	ref?: (el: HTMLTableRowElement | null) => void;
	onPointerDown?: () => void;
};

export function useRowKeys(opts: {
	count: number;
	enabled?: boolean;
	// An action returning false leaves the key to the browser (e.g. space on a focused button).
	actions?: Record<string, (index: number) => unknown>;
}): {
	sel: number;
	setSel: (i: number) => void;
	rowProps: (i: number, className?: string) => RowProps;
} {
	const { count, enabled = true } = opts;
	const [rawSel, setSel] = useState(0);
	const sel = Math.max(0, Math.min(rawSel, count - 1));
	const actions = useRef(opts.actions);
	actions.current = opts.actions;
	const rowEl = useRef<HTMLTableRowElement | null>(null);
	// Scroll only after a keyboard move, not on first render or when rows change under the cursor.
	const moved = useRef(false);

	// Install shortcuts as soon as the rows are committed, before a user can
	// interact with the newly visible list.
	useLayoutEffect(() => {
		if (!enabled) return;
		function onKey(e: KeyboardEvent) {
			if (count === 0 || shouldIgnoreKey(e)) return;
			const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
			if (key === "j" || key === "ArrowDown") {
				moved.current = true;
				setSel(Math.min(sel + 1, count - 1));
			} else if (key === "k" || key === "ArrowUp") {
				moved.current = true;
				setSel(Math.max(sel - 1, 0));
			} else {
				const action = actions.current?.[key];
				if (!action || action(sel) === false) return;
			}
			e.preventDefault();
		}
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [enabled, count, sel]);

	// biome-ignore lint/correctness/useExhaustiveDependencies: sel is the trigger, not read in the body
	useEffect(() => {
		if (!moved.current) return;
		moved.current = false;
		rowEl.current?.scrollIntoView?.({ block: "nearest" });
	}, [sel]);

	const setRow = useCallback((el: HTMLTableRowElement | null) => {
		rowEl.current = el;
	}, []);

	// A click moves the cursor too, so mouse and keyboard agree on the current row.
	const rowProps = useCallback(
		(i: number, className?: string): RowProps => {
			if (!enabled) return className ? { className } : {};
			if (i !== sel) {
				const props: RowProps = { onPointerDown: () => setSel(i) };
				if (className) props.className = className;
				return props;
			}
			return {
				className: className ? `${className} sel` : "sel",
				"aria-selected": true,
				ref: setRow,
			};
		},
		[sel, setRow, enabled],
	);

	return { sel, setSel, rowProps };
}

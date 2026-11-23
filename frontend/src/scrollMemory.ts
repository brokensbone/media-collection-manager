import { useEffect, useLayoutEffect, useRef } from "react";

const positions = new Map<string, number>();

function scrollToY(y: number): void {
	if (window.scrollY !== y) window.scrollTo(0, y);
}

// Back/forward return to where you were on that view; a new view starts at the top. Lists load
// after the route changes, so the restore waits (briefly) until the page is tall enough.
export function useScrollMemory(hash: string, path: string): void {
	const popped = useRef(false);
	const lastPath = useRef(path);
	const restoring = useRef(0);

	useEffect(() => {
		if ("scrollRestoration" in window.history)
			window.history.scrollRestoration = "manual";
		let frame = 0;
		const onScroll = () => {
			if (frame || restoring.current) return;
			frame = requestAnimationFrame(() => {
				frame = 0;
				positions.set(window.location.hash, window.scrollY);
			});
		};
		const onPop = () => {
			popped.current = true;
		};
		window.addEventListener("scroll", onScroll, { passive: true });
		window.addEventListener("popstate", onPop);
		return () => {
			window.removeEventListener("scroll", onScroll);
			window.removeEventListener("popstate", onPop);
			cancelAnimationFrame(frame);
		};
	}, []);

	useLayoutEffect(() => {
		const viewChanged = path !== lastPath.current;
		lastPath.current = path;
		cancelAnimationFrame(restoring.current);
		restoring.current = 0;
		if (popped.current) {
			popped.current = false;
			const target = positions.get(hash) ?? 0;
			const until = performance.now() + 2500;
			const step = () => {
				const max = document.documentElement.scrollHeight - window.innerHeight;
				if (max >= target || performance.now() > until) {
					scrollToY(Math.min(target, Math.max(0, max)));
					restoring.current = 0;
					return;
				}
				restoring.current = requestAnimationFrame(step);
			};
			restoring.current = requestAnimationFrame(step);
		} else if (viewChanged) scrollToY(0);
	}, [hash, path]);
}

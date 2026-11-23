import { useCallback, useSyncExternalStore } from "react";

// The hash is `#<path>?<params>`. Everything that reads or writes the URL goes through here so
// views never overwrite each other's params.

export function parseHash(hash: string = window.location.hash): {
	path: string;
	params: URLSearchParams;
} {
	const raw = hash.replace(/^#/, "");
	const i = raw.indexOf("?");
	if (i === -1) return { path: raw, params: new URLSearchParams() };
	return {
		path: raw.slice(0, i),
		params: new URLSearchParams(raw.slice(i + 1)),
	};
}

function buildHash(path: string, params: URLSearchParams): string {
	const qs = params.toString();
	return qs ? `#${path}?${qs}` : `#${path}`;
}

function commit(next: string, replace: boolean): void {
	if (next === window.location.hash || (next === "#" && !window.location.hash))
		return;
	const oldURL = window.location.href;
	const url = `${window.location.pathname}${window.location.search}${next}`;
	if (replace) window.history.replaceState(window.history.state, "", url);
	else window.history.pushState(null, "", url);
	// pushState/replaceState never fire hashchange on their own.
	window.dispatchEvent(
		new HashChangeEvent("hashchange", { oldURL, newURL: window.location.href }),
	);
}

export function setHashParams(
	patch: Record<string, string | number | null>,
	opts: { replace?: boolean } = {},
): void {
	const { path, params } = parseHash();
	for (const [key, value] of Object.entries(patch)) {
		if (value === null || value === "") params.delete(key);
		else params.set(key, String(value));
	}
	commit(buildHash(path, params), opts.replace ?? false);
}

// Navigate to a path, dropping every param (as a nav link does).
export function setHashPath(
	path: string,
	opts: { replace?: boolean } = {},
): void {
	commit(buildHash(path, new URLSearchParams()), opts.replace ?? false);
}

function subscribe(onChange: () => void): () => void {
	window.addEventListener("hashchange", onChange);
	window.addEventListener("popstate", onChange);
	return () => {
		window.removeEventListener("hashchange", onChange);
		window.removeEventListener("popstate", onChange);
	};
}

function getHash(): string {
	return window.location.hash;
}

// The raw hash, re-rendering on every change.
export function useHash(): string {
	return useSyncExternalStore(subscribe, getHash, () => "");
}

export function useHashParam(
	key: string,
): [
	string | null,
	(value: string | null, opts?: { replace?: boolean }) => void,
] {
	const value = parseHash(useHash()).params.get(key);
	const set = useCallback(
		(v: string | null, opts?: { replace?: boolean }) =>
			setHashParams({ [key]: v }, opts),
		[key],
	);
	return [value, set];
}

export function useQuery(): string {
	return useHashParam("q")[0] ?? "";
}

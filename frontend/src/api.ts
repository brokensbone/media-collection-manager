// Many test stubs return `{ json }` with no `ok`, so only an explicit `ok: false` is a failure.
export async function fetchJson<T>(
	url: string,
	init?: RequestInit,
): Promise<T> {
	// Tests assert toHaveBeenCalledWith(url), which a trailing undefined argument would fail.
	const res = await (init ? fetch(url, init) : fetch(url));
	if (res.ok === false) throw new Error(`${url} responded ${res.status}`);
	return (await res.json()) as T;
}

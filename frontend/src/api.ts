// Many test stubs return `{ json }` with no `ok`, so only an explicit `ok: false` is a failure.
export async function fetchJson<T>(
	url: string,
	init?: RequestInit,
): Promise<T> {
	const res = await fetch(url, init);
	if (res.ok === false) throw new Error(`${url} responded ${res.status}`);
	return (await res.json()) as T;
}

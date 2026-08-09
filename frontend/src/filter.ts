// Case-insensitive, token-AND substring match: every whitespace-separated token in the query
// must appear somewhere in the haystack. So "porri ev" matches "Porridge Radio Every Bad".
// An empty query matches everything.
export function matchesQuery(haystack: string, query: string): boolean {
	const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
	const h = haystack.toLowerCase();
	return tokens.every((t) => h.includes(t));
}

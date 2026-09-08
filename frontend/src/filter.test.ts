import { describe, expect, it } from "vitest";
import { matchesQuery } from "./filter";

describe("matchesQuery", () => {
	it("matches when every token is a substring, across the whole haystack", () => {
		expect(matchesQuery("Porridge Radio Every Bad", "porri ev")).toBe(true);
	});

	it("is case-insensitive", () => {
		expect(matchesQuery("Burial Untrue", "BURIAL")).toBe(true);
	});

	it("fails if any token is absent", () => {
		expect(matchesQuery("Porridge Radio Every Bad", "porri xyz")).toBe(false);
	});

	it("an empty query matches everything", () => {
		expect(matchesQuery("anything", "   ")).toBe(true);
	});
});

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SpotifyStatus } from "./SpotifyStatus";

function mockStatus(body: unknown) {
	vi.stubGlobal(
		"fetch",
		vi.fn(() => Promise.resolve({ json: () => Promise.resolve(body) })),
	);
}

afterEach(() => {
	cleanup(); // globals:false, so RTL's auto-cleanup isn't registered
	vi.unstubAllGlobals();
});

describe("SpotifyStatus", () => {
	it("offers connect when disconnected", async () => {
		mockStatus({
			connected: false,
			authorized_at: null,
			reauth_in_days: null,
			reauth_due: true,
		});
		render(<SpotifyStatus />);
		const link = await screen.findByRole("link");
		expect(link.getAttribute("href")).toBe("/auth/spotify/login");
		expect(link.textContent).toContain("Connect");
	});

	it('shows just "Spotify" when connected, with the countdown in a tooltip', async () => {
		mockStatus({
			connected: true,
			authorized_at: "2026-04-01T00:00:00Z",
			reauth_in_days: 83,
			reauth_due: false,
		});
		render(<SpotifyStatus />);
		const el = await screen.findByText("Spotify");
		expect(el.getAttribute("title")).toBe("Connected · reauth in 83d");
		expect(screen.queryByRole("link")).toBeNull();
	});

	it("surfaces a Reconnect link when reauth is due", async () => {
		mockStatus({
			connected: true,
			authorized_at: "2026-01-01T00:00:00Z",
			reauth_in_days: 5,
			reauth_due: true,
		});
		render(<SpotifyStatus />);
		const link = await screen.findByRole("link", { name: "Reconnect" });
		expect(link.getAttribute("href")).toBe("/auth/spotify/login");
	});
});

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Acquire } from "./Acquire";

function mockApi(items: unknown, candidates: unknown = []) {
  const fetchMock = vi.fn((url: string, opts?: { method?: string }) => {
    if (opts?.method === "POST") return Promise.resolve({ ok: true });
    if (url.includes("/library/search"))
      return Promise.resolve({ json: () => Promise.resolve(candidates) });
    return Promise.resolve({ json: () => Promise.resolve(items) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function item(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    artist: "A",
    title: "T1",
    has_art: false,
    bandcamp_url: "https://bandcamp.com/search?q=A+T1",
    possibly_owned: false,
    owned_hint: null,
    ...over,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Acquire", () => {
  it("shows a Bandcamp buy link per item", async () => {
    mockApi([item()]);
    render(<Acquire />);
    const link = await screen.findByRole("link", { name: "Bandcamp" });
    expect(link.getAttribute("href")).toBe(
      "https://bandcamp.com/search?q=A+T1",
    );
  });

  it("shows Red + Ops tracker search links (artist+title tab-separated) per item", async () => {
    mockApi([item({ artist: "Horse Meat Disco", title: "Love And Dancing" })]);
    render(<Acquire />);
    const red = await screen.findByRole("link", { name: "Red" });
    expect(red.getAttribute("href")).toBe(
      "https://redacted.sh/torrents.php?searchstr=Horse+Meat+Disco%09Love+And+Dancing",
    );
    const ops = await screen.findByRole("link", { name: "Ops" });
    expect(ops.getAttribute("href")).toBe(
      "https://orpheus.network/torrents.php?searchstr=Horse+Meat+Disco%09Love+And+Dancing" +
        "&tags_type=1&order=time&sort=desc&group_results=1&action=basic&searchsubmit=1",
    );
  });

  it("has no Mark ordered action", async () => {
    mockApi([item()]);
    render(<Acquire />);
    await screen.findByText("T1");
    expect(screen.queryByRole("button", { name: /ordered/i })).toBeNull();
  });

  it("filters rows by the query across artist and title", async () => {
    mockApi([
      item({ id: 1, artist: "Porridge Radio", title: "Every Bad" }),
      item({ id: 2, artist: "Burial", title: "Untrue" }),
    ]);
    render(<Acquire query="porri ev" />);
    expect(await screen.findByText("Every Bad")).toBeTruthy();
    expect(screen.queryByText("Untrue")).toBeNull();
  });

  it("flags a possibly-owned want with its hint", async () => {
    mockApi([item({ possibly_owned: true, owned_hint: "A — T1 (Deluxe)" })]);
    render(<Acquire />);
    expect(
      await screen.findByText(/possibly owned: A — T1 \(Deluxe\)/),
    ).toBeTruthy();
  });

  it("mark owned opens a modal, searches the library, and links the chosen album", async () => {
    const fetchMock = mockApi(
      [item({ id: 9, title: "Only" })],
      [
        {
          beets_id: "b7",
          artist: "A",
          title: "Only (Remaster)",
          has_release_group: true,
          score: 0.9,
        },
      ],
    );
    render(<Acquire />);
    await screen.findByText("Only");
    fireEvent.click(screen.getByRole("button", { name: "Mark owned…" }));

    expect(await screen.findByRole("dialog")).toBeTruthy();
    const result = await screen.findByRole("button", {
      name: /Only \(Remaster\)/,
    });
    fireEvent.click(result);
    await screen.findByText(/Nothing to acquire/);

    const posted = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
    expect(posted?.[0]).toBe("/albums/9/mark-owned");
    expect(JSON.parse((posted?.[1] as { body: string }).body)).toEqual({
      beets_id: "b7",
    });
  });

  it("mark owned without a link posts a null beets_id", async () => {
    const fetchMock = mockApi([item({ id: 9, title: "Only" })]);
    render(<Acquire />);
    await screen.findByText("Only");
    fireEvent.click(screen.getByRole("button", { name: "Mark owned…" }));
    const noLink = await screen.findByRole("button", {
      name: "Mark owned without a link",
    });
    fireEvent.click(noLink);
    await screen.findByText(/Nothing to acquire/);

    const posted = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
    expect(posted?.[0]).toBe("/albums/9/mark-owned");
    expect(JSON.parse((posted?.[1] as { body: string }).body)).toEqual({
      beets_id: null,
    });
  });

  it("can return a wanted album to saved", async () => {
    const fetchMock = mockApi([item({ id: 9, title: "Only" })]);
    render(<Acquire />);
    await screen.findByText("Only");
    fireEvent.click(screen.getByRole("button", { name: "Back to saved" }));
    await screen.findByText(/Nothing to acquire/);

    const posted = fetchMock.mock.calls.find(
      (c) => c[0] === "/albums/9/return-to-saved",
    );
    expect(posted?.[1]).toEqual({ method: "POST" });
  });
});

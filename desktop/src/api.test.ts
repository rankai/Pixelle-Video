import { beforeEach, describe, expect, it, vi } from "vitest";

import { markPublishRunOutcomeV2 } from "./api";

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

describe("publish API safety mappings", () => {
  beforeEach(() => {
    invoke.mockRejectedValue(new Error("browser test"));
    vi.restoreAllMocks();
  });

  it("maps a user cancellation to the backend abandoned outcome", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ run: {} }), { status: 200, headers: { "content-type": "application/json" } }));
    await markPublishRunOutcomeV2("run_1", "not_published");
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toMatchObject({ outcome: "abandoned_by_user", actor_ref: "desktop_user" });
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createJob, fileUrl, safeHref, safeImageSrc } from "./api.js";

describe("safeHref", () => {
  it.each([
    ["https://wa.me/628123", "https://wa.me/628123"],
    ["tel:+62217201234", "tel:+62217201234"],
    ["javascript:alert(1)", null],
    ["data:text/html,<script>", null],
    ["not a url", null],
    ["", null],
  ])("%s -> %s", (input, expected) => {
    expect(safeHref(input)).toBe(expected);
  });
});

describe("url builders", () => {
  const id = "0123456789abcdef0123456789abcdef";

  it("accepts only same-origin job image paths", () => {
    expect(safeImageSrc(`/api/jobs/${id}/images/Kopi_A_node_123_1.jpg`)).toBe(`/api/jobs/${id}/images/Kopi_A_node_123_1.jpg`);
    expect(safeImageSrc(`https://evil.com/api/jobs/${id}/images/x.jpg`)).toBeNull();
    expect(safeImageSrc(`/api/jobs/${id}/images/../../secret.jpg`)).toBeNull();
    expect(safeImageSrc("javascript:alert(1)")).toBeNull();
    expect(safeImageSrc(undefined)).toBeNull();
    expect(fileUrl("abc", "csv")).toBe("/api/jobs/abc/files/csv");
  });
});

describe("createJob", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("maps payload and returns body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ id: "1" }) });
    vi.stubGlobal("fetch", fetchMock);

    await expect(createJob({ keyword: "salon", area: "Jakarta Selatan", maxResults: 20 })).resolves.toEqual({ id: "1" });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      keyword: "salon",
      area: "Jakarta Selatan",
      max_results: 20,
      price_min: null,
      price_max: null,
    });
  });

  it("surfaces server detail as ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422, json: () => Promise.resolve({ detail: "Input tidak valid" }) }));
    await expect(createJob({})).rejects.toMatchObject({ name: "ApiError", message: "Input tidak valid", status: 422 });
  });

  it("reports unreachable server", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(createJob({})).rejects.toBeInstanceOf(ApiError);
  });
});

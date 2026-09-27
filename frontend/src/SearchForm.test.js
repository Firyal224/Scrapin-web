import { describe, expect, it } from "vitest";
import { formatPrice, parsePrice, validate } from "./components/SearchForm.jsx";

const base = { keyword: "cafe", area: "Jakarta Selatan", maxResults: 20, priceMin: null, priceMax: null };

describe("price helpers", () => {
  it("parses and formats rupiah input", () => {
    expect(parsePrice("Rp 50.000")).toBe(50000);
    expect(parsePrice("")).toBeNull();
    expect(formatPrice(1250000)).toBe("1.250.000");
    expect(formatPrice("")).toBe("");
  });
});

describe("validate", () => {
  it("accepts empty price range", () => {
    expect(validate(base)).toBe("");
  });

  it("rejects min greater than max", () => {
    expect(validate({ ...base, priceMin: 100000, priceMax: 50000 })).toMatch(/minimum/);
  });

  it("rejects prices above the limit", () => {
    expect(validate({ ...base, priceMax: 20_000_000 })).toMatch(/10\.000\.000/);
  });
});

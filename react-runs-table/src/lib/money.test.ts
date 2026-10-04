import { formatUsd, parseUsd, percentOf, sumMicro, toUsdString } from "./money";

describe("parseUsd", () => {
  it("parses API strings exactly into micro-dollars", () => {
    expect(parseUsd("0.712900")).toBe(712_900n);
    expect(parseUsd("0.057860")).toBe(57_860n);
    expect(parseUsd("3")).toBe(3_000_000n);
    expect(parseUsd("-0.5")).toBe(-500_000n);
  });

  it("rejects malformed or over-precise values instead of guessing", () => {
    expect(() => parseUsd("abc")).toThrow();
    expect(() => parseUsd("0.0000001")).toThrow();
    expect(() => parseUsd("1e-3")).toThrow();
  });

  it("sums without float drift", () => {
    expect(0.1 + 0.2).not.toBe(0.3); // why the contract forbids Number
    expect(sumMicro([parseUsd("0.100000"), parseUsd("0.200000")])).toBe(300_000n);
  });
});

describe("formatUsd", () => {
  it("uses one format with 4 decimals and half-up rounding", () => {
    expect(formatUsd(712_900n)).toBe("$0.7129");
    expect(formatUsd(87_430n)).toBe("$0.0874");
    expect(formatUsd(87_450n)).toBe("$0.0875");
    expect(formatUsd(0n)).toBe("$0.0000");
    expect(formatUsd(1_234_567_890n)).toBe("$1,234.5679");
    expect(formatUsd(-12_360n)).toBe("-$0.0124");
    expect(formatUsd(258_108n, 6)).toBe("$0.258108");
  });

  it("round-trips to the wire format", () => {
    expect(toUsdString(260_000n)).toBe("0.260000");
  });
});

describe("percentOf", () => {
  it("does not cap overruns at 100%", () => {
    expect(percentOf(parseUsd("0.258108"), parseUsd("0.057860"))).toBe(446);
  });
  it("rounds half up", () => {
    expect(percentOf(712_900n, 950_000n)).toBe(75);
    expect(percentOf(712_900n, 350_000n)).toBe(204);
    expect(percentOf(5n, 1000n)).toBe(1);
  });
  it("returns null for a zero budget instead of Infinity", () => {
    expect(percentOf(1n, 0n)).toBeNull();
  });
});

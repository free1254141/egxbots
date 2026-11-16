import {
  extractClientIp,
  hashTrialSignal,
  isDisposableEmail,
  normalizeCanonicalEmail,
} from "../trial-anti-abuse";

describe("trial-anti-abuse helpers", () => {
  it("normalizes Gmail dots, googlemail domain, and +aliases", () => {
    expect(normalizeCanonicalEmail("A.B.C+promo@gmail.com")).toBe("abc@gmail.com");
    expect(normalizeCanonicalEmail("test.user+egx@googlemail.com")).toBe("testuser@gmail.com");
    expect(normalizeCanonicalEmail("user.name+tag@yahoo.com")).toBe("user.name@yahoo.com");
  });

  it("detects disposable temporary email domains", () => {
    expect(isDisposableEmail("spammer@yopmail.com")).toBe(true);
    expect(isDisposableEmail("user@mohmal.com")).toBe(true);
    expect(isDisposableEmail("real.user@gmail.com")).toBe(false);
  });

  it("produces deterministic non-empty hashes for valid signals and null for empty", () => {
    const h1 = hashTrialSignal("197.55.12.1");
    const h2 = hashTrialSignal("197.55.12.1");
    const h3 = hashTrialSignal("197.55.12.2");
    expect(h1).toBeTruthy();
    expect(h1).toBe(h2);
    expect(h1).not.toBe(h3);
    expect(hashTrialSignal("  ")).toBeNull();
  });

  it("extracts first client IP from x-forwarded-for or falls back to x-real-ip", () => {
    const req1 = new Request("https://egxbots.com/api/subscription/trial", {
      headers: { "x-forwarded-for": "41.44.10.2, 10.0.0.1" },
    });
    expect(extractClientIp(req1)).toBe("41.44.10.2");

    const req2 = new Request("https://egxbots.com/api/subscription/trial", {
      headers: { "x-real-ip": "156.200.1.9" },
    });
    expect(extractClientIp(req2)).toBe("156.200.1.9");
  });
});

import { beforeEach, describe, expect, it } from "vitest";

import {
  checkRateLimit,
  resetRateLimitsForTests,
} from "@/lib/security/rate-limit";

describe("request rate limit", () => {
  beforeEach(resetRateLimitsForTests);

  it("allows five requests and blocks the sixth within ten minutes", () => {
    const now = 10_000_000;
    for (let index = 0; index < 5; index += 1) {
      expect(checkRateLimit("client", now + index).allowed).toBe(true);
    }

    const blocked = checkRateLimit("client", now + 5);
    expect(blocked.allowed).toBe(false);
    expect(blocked.retryAfterSeconds).toBeGreaterThan(0);
  });

  it("allows a new request after the window expires", () => {
    const now = 10_000_000;
    for (let index = 0; index < 5; index += 1) {
      checkRateLimit("client", now + index);
    }

    expect(checkRateLimit("client", now + 10 * 60 * 1000 + 1).allowed).toBe(
      true,
    );
  });
});

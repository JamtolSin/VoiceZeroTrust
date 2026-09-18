import { createHash } from "node:crypto";

const WINDOW_MS = 10 * 60 * 1000;
const MAX_REQUESTS = 5;
const buckets = new Map<string, number[]>();

export type RateLimitResult = {
  allowed: boolean;
  retryAfterSeconds: number;
};

export function getAnonymousClientKey(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  const address = forwarded || request.headers.get("x-real-ip") || "local";
  return createHash("sha256").update(address).digest("hex").slice(0, 24);
}

export function checkRateLimit(
  key: string,
  now = Date.now(),
): RateLimitResult {
  const cutoff = now - WINDOW_MS;
  const recent = (buckets.get(key) ?? []).filter((time) => time > cutoff);

  if (recent.length >= MAX_REQUESTS) {
    buckets.set(key, recent);
    return {
      allowed: false,
      retryAfterSeconds: Math.max(
        1,
        Math.ceil((recent[0] + WINDOW_MS - now) / 1000),
      ),
    };
  }

  recent.push(now);
  buckets.set(key, recent);

  if (buckets.size > 5_000) {
    for (const [bucketKey, times] of buckets) {
      if (times.every((time) => time <= cutoff)) buckets.delete(bucketKey);
    }
  }

  return { allowed: true, retryAfterSeconds: 0 };
}

export function resetRateLimitsForTests(): void {
  buckets.clear();
}

import { describe, expect, it } from "vitest";

import {
  isSafePhraseId,
  SAFE_PHRASES,
} from "@/lib/attack/constants";

describe("safe phrases", () => {
  it("accepts only server-owned phrase ids", () => {
    expect(isSafePhraseId("never_spoken")).toBe(true);
    expect(isSafePhraseId("send_money_now")).toBe(false);
    expect(isSafePhraseId({ text: SAFE_PHRASES.never_spoken })).toBe(false);
  });

  it("keeps every phrase explicitly marked as AI test content", () => {
    expect(Object.keys(SAFE_PHRASES)).toEqual([
      "ai_disclosure",
      "never_spoken",
      "ten_seconds",
    ]);
    expect(SAFE_PHRASES.ai_disclosure).toContain("인공지능");
  });
});

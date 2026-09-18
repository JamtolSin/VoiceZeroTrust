import { describe, expect, it } from "vitest";

import { consumeAttackStream, encodeStreamEvent } from "@/lib/attack/stream";
import type { AttackStreamEvent } from "@/types/attack";

describe("NDJSON attack stream", () => {
  it("parses events split across transport chunks", async () => {
    const first: AttackStreamEvent = {
      type: "status",
      stage: "cloning",
      elapsedMs: 12,
      message: "cloning",
    };
    const second: AttackStreamEvent = {
      type: "error",
      error: {
        code: "PROVIDER_FAILED",
        message: "failed",
        retryable: true,
        requestId: "request-id",
      },
    };
    const combined = new Uint8Array([
      ...encodeStreamEvent(first),
      ...encodeStreamEvent(second),
    ]);
    const response = new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(combined.slice(0, 17));
          controller.enqueue(combined.slice(17));
          controller.close();
        },
      }),
    );
    const received: AttackStreamEvent[] = [];

    await consumeAttackStream(response, (event) => received.push(event));

    expect(received).toEqual([first, second]);
  });
});

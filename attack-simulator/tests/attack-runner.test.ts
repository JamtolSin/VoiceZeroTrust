import { describe, expect, it } from "vitest";

import { AttackError } from "@/lib/attack/errors";
import { runVoiceCloneAttack } from "@/lib/attack/runner";
import type { VoiceCloneProvider } from "@/lib/voice/provider";

const audio = {
  bytes: new Uint8Array([1, 2, 3]),
  mimeType: "audio/wav" as const,
  filename: "voice-sample.wav",
  durationMs: 10_000,
  sampleRate: 16_000,
  channels: 1,
  rms: 0.1,
  peak: 0.2,
};

function provider(overrides: Partial<VoiceCloneProvider> = {}) {
  let deleted = 0;
  const implementation: VoiceCloneProvider = {
    name: "mock",
    async createClone() {
      return { id: "clone-id", state: "created" };
    },
    async waitUntilReady({ clone }) {
      return { ...clone, state: "trained" };
    },
    async generateSpeech() {
      return { bytes: new Uint8Array([9, 8, 7]), mimeType: "audio/wav" };
    },
    async deleteClone() {
      deleted += 1;
    },
    ...overrides,
  };
  return { implementation, deleted: () => deleted };
}

describe("voice clone attack runner", () => {
  it("generates speech and cleans up the clone", async () => {
    const mock = provider();
    const stages: string[] = [];
    const result = await runVoiceCloneAttack({
      audio,
      phrase: "테스트 문장",
      requestId: "request-id",
      validationMs: 3,
      provider: mock.implementation,
      signal: new AbortController().signal,
      onStage(stage) {
        stages.push(stage);
      },
    });

    expect(result.audio.bytes).toEqual(new Uint8Array([9, 8, 7]));
    expect(result.cleanupCompleted).toBe(true);
    expect(mock.deleted()).toBe(1);
    expect(stages).toEqual(["cloning", "generating", "cleaning"]);
    expect(result.timings.recordingMs).toBe(10_000);
  });

  it("still deletes the clone when speech generation fails", async () => {
    const failure = new AttackError(
      "PROVIDER_FAILED",
      "provider failed",
      true,
      502,
    );
    const mock = provider({
      async generateSpeech() {
        throw failure;
      },
    });

    await expect(
      runVoiceCloneAttack({
        audio,
        phrase: "테스트 문장",
        requestId: "request-id",
        validationMs: 2,
        provider: mock.implementation,
        signal: new AbortController().signal,
        onStage() {},
      }),
    ).rejects.toBe(failure);
    expect(mock.deleted()).toBe(1);
  });

  it("reports cleanup failure without discarding a generated result", async () => {
    const mock = provider({
      async deleteClone() {
        throw new Error("delete failed");
      },
    });
    const result = await runVoiceCloneAttack({
      audio,
      phrase: "테스트 문장",
      requestId: "request-id",
      validationMs: 2,
      provider: mock.implementation,
      signal: new AbortController().signal,
      onStage() {},
    });

    expect(result.cleanupCompleted).toBe(false);
  });

  it("uses a fresh cleanup signal after the user cancels", async () => {
    const controller = new AbortController();
    let cleanupSignalWasAborted = true;
    const mock = provider({
      async generateSpeech() {
        controller.abort();
        throw new AttackError(
          "REQUEST_CANCELLED",
          "request cancelled",
          true,
          499,
        );
      },
      async deleteClone({ signal }) {
        cleanupSignalWasAborted = signal.aborted;
      },
    });

    await expect(
      runVoiceCloneAttack({
        audio,
        phrase: "테스트 문장",
        requestId: "request-id",
        validationMs: 2,
        provider: mock.implementation,
        signal: controller.signal,
        onStage() {},
      }),
    ).rejects.toMatchObject({ code: "REQUEST_CANCELLED" });
    expect(cleanupSignalWasAborted).toBe(false);
  });
});

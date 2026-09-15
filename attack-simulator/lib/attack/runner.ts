import { setTimeout as delay } from "node:timers/promises";

import { AttackError } from "@/lib/attack/errors";
import { REFERENCE_PROMPT } from "@/lib/attack/constants";
import type { ValidatedAudio } from "@/lib/audio/wav";
import type { VoiceCloneProvider } from "@/lib/voice/provider";
import type { AttackStage, AttackTimings } from "@/types/attack";

const CLEANUP_ATTEMPTS = 3;

export type AttackRunnerResult = {
  provider: "fish-audio" | "mock";
  audio: { bytes: Uint8Array; mimeType: string };
  timings: AttackTimings;
  cleanupCompleted: boolean;
};

type StageReporter = (
  stage: AttackStage,
  elapsedMs: number,
  message: string,
) => void;

async function deleteWithRetry(
  provider: VoiceCloneProvider,
  clone: Awaited<ReturnType<VoiceCloneProvider["createClone"]>>,
  signal: AbortSignal,
): Promise<boolean> {
  for (let attempt = 1; attempt <= CLEANUP_ATTEMPTS; attempt += 1) {
    try {
      await provider.deleteClone({ clone, signal });
      return true;
    } catch {
      if (attempt < CLEANUP_ATTEMPTS && !signal.aborted) {
        await delay(250 * attempt, undefined, { signal }).catch(() => undefined);
      }
    }
  }
  return false;
}

export async function runVoiceCloneAttack(input: {
  audio: ValidatedAudio;
  phrase: string;
  requestId: string;
  validationMs: number;
  provider: VoiceCloneProvider;
  signal: AbortSignal;
  onStage: StageReporter;
}): Promise<AttackRunnerResult> {
  const startedAt = performance.now();
  let clone:
    | Awaited<ReturnType<VoiceCloneProvider["createClone"]>>
    | undefined;
  let generated:
    | Awaited<ReturnType<VoiceCloneProvider["generateSpeech"]>>
    | undefined;
  let cloneMs = 0;
  let generationMs = 0;
  let cleanupMs = 0;
  let cleanupCompleted = true;
  let thrown: unknown;

  try {
    input.onStage("cloning", 0, "10초 음성으로 Voice Clone을 준비하고 있습니다.");
    const cloneStartedAt = performance.now();
    clone = await input.provider.createClone({
      audio: input.audio,
      referenceText: REFERENCE_PROMPT,
      requestId: input.requestId,
      signal: input.signal,
    });
    clone = await input.provider.waitUntilReady({
      clone,
      signal: input.signal,
    });
    cloneMs = performance.now() - cloneStartedAt;

    input.onStage(
      "generating",
      performance.now() - startedAt,
      "선택한 안전 문장을 새 음성으로 생성하고 있습니다.",
    );
    const generationStartedAt = performance.now();
    generated = await input.provider.generateSpeech({
      clone,
      text: input.phrase,
      requestId: input.requestId,
      signal: input.signal,
    });
    generationMs = performance.now() - generationStartedAt;
  } catch (error) {
    thrown = error;
  } finally {
    if (clone) {
      input.onStage(
        "cleaning",
        performance.now() - startedAt,
        "외부 Provider의 임시 Voice Clone을 삭제하고 있습니다.",
      );
      const cleanupStartedAt = performance.now();
      const cleanupSignal = input.signal.aborted
        ? AbortSignal.timeout(5_000)
        : input.signal;
      cleanupCompleted = await deleteWithRetry(
        input.provider,
        clone,
        cleanupSignal,
      );
      cleanupMs = performance.now() - cleanupStartedAt;
    }
  }

  if (thrown) throw thrown;
  if (!generated) {
    throw new AttackError(
      "PROVIDER_FAILED",
      "생성된 음성을 확인할 수 없습니다.",
      true,
      502,
    );
  }

  const totalMs = performance.now() - startedAt;
  return {
    provider: input.provider.name,
    audio: generated,
    cleanupCompleted,
    timings: {
      recordingMs: input.audio.durationMs,
      validationMs: input.validationMs,
      cloneMs,
      generationMs,
      cleanupMs,
      totalMs,
    },
  };
}

import { setTimeout as delay } from "node:timers/promises";

import { encodePcm16Wav } from "@/lib/audio/wav";
import type {
  CloneReference,
  GeneratedAudio,
  VoiceCloneProvider,
} from "@/lib/voice/provider";

function getDelayMs(): number {
  if (process.env.NODE_ENV === "test") return 0;
  const configured = Number(process.env.MOCK_PROVIDER_DELAY_MS);
  return Number.isFinite(configured) && configured >= 0 ? configured : 250;
}

async function simulatedDelay(signal: AbortSignal): Promise<void> {
  const duration = getDelayMs();
  if (duration > 0) await delay(duration, undefined, { signal });
}

export class MockVoiceProvider implements VoiceCloneProvider {
  readonly name = "mock" as const;

  async createClone({
    requestId,
    signal,
  }: Parameters<VoiceCloneProvider["createClone"]>[0]): Promise<CloneReference> {
    await simulatedDelay(signal);
    return { id: `mock-${requestId}`, state: "created" };
  }

  async waitUntilReady({
    clone,
    signal,
  }: Parameters<VoiceCloneProvider["waitUntilReady"]>[0]): Promise<CloneReference> {
    await simulatedDelay(signal);
    return { ...clone, state: "trained" };
  }

  async generateSpeech({
    signal,
  }: Parameters<VoiceCloneProvider["generateSpeech"]>[0]): Promise<GeneratedAudio> {
    await simulatedDelay(signal);
    const sampleRate = 16_000;
    const durationSeconds = 1.8;
    const samples = new Float32Array(sampleRate * durationSeconds);

    for (let index = 0; index < samples.length; index += 1) {
      const segment = Math.floor(index / (sampleRate * 0.3));
      const frequency = segment % 2 === 0 ? 220 : 330;
      const envelope = Math.min(1, index / 500, (samples.length - index) / 500);
      samples[index] =
        Math.sin((2 * Math.PI * frequency * index) / sampleRate) *
        0.16 *
        envelope;
    }

    return { bytes: encodePcm16Wav(samples), mimeType: "audio/wav" };
  }

  async deleteClone({
    signal,
  }: Parameters<VoiceCloneProvider["deleteClone"]>[0]): Promise<void> {
    await simulatedDelay(signal);
  }
}

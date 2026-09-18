import { describe, expect, it } from "vitest";

import { encodePcm16Wav, validatePcm16Wav } from "@/lib/audio/wav";
import { AttackError } from "@/lib/attack/errors";

function sineWave(durationSeconds: number, amplitude = 0.15): Float32Array {
  const sampleRate = 16_000;
  const samples = new Float32Array(Math.round(durationSeconds * sampleRate));
  for (let index = 0; index < samples.length; index += 1) {
    samples[index] =
      Math.sin((2 * Math.PI * 220 * index) / sampleRate) * amplitude;
  }
  return samples;
}

function expectCode(action: () => unknown, code: AttackError["code"]): void {
  try {
    action();
    throw new Error("Expected validation to fail");
  } catch (error) {
    expect(error).toBeInstanceOf(AttackError);
    expect((error as AttackError).code).toBe(code);
  }
}

describe("PCM WAV validation", () => {
  it("accepts a ten second 16kHz mono recording", () => {
    const audio = validatePcm16Wav(encodePcm16Wav(sineWave(10)));

    expect(audio.durationMs).toBe(10_000);
    expect(audio.sampleRate).toBe(16_000);
    expect(audio.channels).toBe(1);
    expect(audio.rms).toBeGreaterThan(0.1);
  });

  it("rejects quiet audio", () => {
    const wav = encodePcm16Wav(new Float32Array(160_000));
    expectCode(() => validatePcm16Wav(wav), "AUDIO_TOO_QUIET");
  });

  it("rejects recordings outside the duration tolerance", () => {
    const wav = encodePcm16Wav(sineWave(9));
    expectCode(() => validatePcm16Wav(wav), "AUDIO_DURATION_INVALID");
  });

  it("rejects malformed audio", () => {
    const bytes = new TextEncoder().encode("not a wave file");
    expectCode(() => validatePcm16Wav(bytes), "AUDIO_FORMAT_INVALID");
  });

  it("rejects payloads above the configured limit", () => {
    const wav = encodePcm16Wav(sineWave(13));
    expectCode(() => validatePcm16Wav(wav), "AUDIO_TOO_LARGE");
  });
});

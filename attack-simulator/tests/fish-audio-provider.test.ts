import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AttackError } from "@/lib/attack/errors";
import { FishAudioProvider } from "@/lib/voice/fish-audio-provider";

const audio = {
  bytes: new Uint8Array([82, 73, 70, 70]),
  mimeType: "audio/wav" as const,
  filename: "voice-sample.wav",
  durationMs: 10_000,
  sampleRate: 16_000,
  channels: 1,
  rms: 0.1,
  peak: 0.2,
};

describe("Fish Audio provider contract", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    process.env.FISH_AUDIO_API_KEY = "test-key";
    process.env.FISH_AUDIO_BASE_URL = "https://fish.test";
    process.env.FISH_AUDIO_MODEL = "s2.1-pro-free";
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    delete process.env.FISH_AUDIO_API_KEY;
    delete process.env.FISH_AUDIO_BASE_URL;
    delete process.env.FISH_AUDIO_MODEL;
    vi.restoreAllMocks();
  });

  it("creates a private clone, generates a fixed phrase, and deletes it", async () => {
    const calls: Array<{ url: string; init: RequestInit }> = [];
    globalThis.fetch = vi.fn(async (input, init = {}) => {
      const url = String(input);
      calls.push({ url, init });

      if (url.endsWith("/model") && init.method === "POST") {
        return Response.json(
          { _id: "model-id", state: "created" },
          { status: 201 },
        );
      }
      if (url.endsWith("/v1/tts")) {
        return new Response(new Uint8Array([1, 2, 3]), {
          headers: { "Content-Type": "audio/mpeg" },
        });
      }
      if (url.endsWith("/model/model-id") && init.method === "DELETE") {
        return new Response(null, { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    }) as typeof fetch;

    const provider = new FishAudioProvider();
    const signal = new AbortController().signal;
    const clone = await provider.createClone({
      audio,
      referenceText: "참조 문장",
      requestId: "request-id",
      signal,
    });
    const ready = await provider.waitUntilReady({ clone, signal });
    const generated = await provider.generateSpeech({
      clone: ready,
      text: "안전 문장",
      requestId: "request-id",
      signal,
    });
    await provider.deleteClone({ clone, signal });

    expect(clone).toEqual({ id: "model-id", state: "created" });
    expect(generated).toEqual({
      bytes: new Uint8Array([1, 2, 3]),
      mimeType: "audio/mpeg",
    });
    expect(calls.map((call) => [call.init.method ?? "GET", call.url])).toEqual([
      ["POST", "https://fish.test/model"],
      ["POST", "https://fish.test/v1/tts"],
      ["DELETE", "https://fish.test/model/model-id"],
    ]);

    const createBody = calls[0].init.body as FormData;
    expect(createBody.get("visibility")).toBe("private");
    expect(createBody.get("train_mode")).toBe("fast");
    expect(createBody.get("texts")).toBe("참조 문장");
    expect(createBody.get("voices")).toBeInstanceOf(File);

    expect(JSON.parse(String(calls[1].init.body))).toMatchObject({
      text: "안전 문장",
      reference_id: "model-id",
      format: "mp3",
    });
    expect(new Headers(calls[1].init.headers).get("model")).toBe(
      "s2.1-pro-free",
    );
  });

  it("maps an invalid API key to a safe public error", async () => {
    globalThis.fetch = vi.fn(async () =>
      Response.json({ message: "private provider detail" }, { status: 401 }),
    ) as typeof fetch;
    const provider = new FishAudioProvider();

    await expect(
      provider.createClone({
        audio,
        referenceText: "참조 문장",
        requestId: "request-id",
        signal: new AbortController().signal,
      }),
    ).rejects.toMatchObject<Partial<AttackError>>({
      code: "PROVIDER_AUTH_FAILED",
      message: "음성 생성 서비스 인증에 실패했습니다.",
    });
  });
});

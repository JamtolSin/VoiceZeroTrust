import { setTimeout as delay } from "node:timers/promises";

import { AttackError } from "@/lib/attack/errors";
import type {
  CloneReference,
  CloneState,
  GeneratedAudio,
  VoiceCloneProvider,
} from "@/lib/voice/provider";

const DEFAULT_BASE_URL = "https://api.fish.audio";
const DEFAULT_MODEL = "s2.1-pro-free";
const DEFAULT_TIMEOUT_MS = 120_000;
const MODEL_POLL_INTERVAL_MS = 1_000;
const MODEL_POLL_LIMIT = 30;
const MAX_GENERATED_AUDIO_BYTES = 2_000_000;

type ModelResponse = {
  _id?: unknown;
  state?: unknown;
};

function isCloneState(value: unknown): value is CloneState {
  return ["created", "training", "trained", "failed"].includes(String(value));
}

function getTimeoutMs(): number {
  const configured = Number(process.env.FISH_AUDIO_TIMEOUT_MS);
  return Number.isFinite(configured) && configured >= 1_000
    ? configured
    : DEFAULT_TIMEOUT_MS;
}

function mapProviderError(status: number, detail: string): AttackError {
  if (status === 401 || status === 403) {
    return new AttackError(
      "PROVIDER_AUTH_FAILED",
      "음성 생성 서비스 인증에 실패했습니다.",
      false,
      502,
    );
  }
  if (status === 429) {
    return new AttackError(
      "PROVIDER_RATE_LIMITED",
      "요청이 많아 음성 생성이 지연되고 있습니다. 잠시 후 다시 시도해주세요.",
      true,
      503,
    );
  }
  if (status === 402 || status === 422) {
    return new AttackError(
      "PROVIDER_REJECTED",
      "음성 생성 서비스가 요청을 처리하지 못했습니다. 새로 녹음해주세요.",
      status === 422,
      502,
      { cause: new Error(detail) },
    );
  }
  return new AttackError(
    "PROVIDER_FAILED",
    "음성 생성 서비스에 일시적인 오류가 발생했습니다.",
    status >= 500,
    502,
    { cause: new Error(detail) },
  );
}

async function safeErrorDetail(response: Response): Promise<string> {
  try {
    return (await response.text()).slice(0, 500);
  } catch {
    return `HTTP ${response.status}`;
  }
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  parentSignal: AbortSignal,
): Promise<Response> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, getTimeoutMs());
  const abortFromParent = () => controller.abort(parentSignal.reason);
  parentSignal.addEventListener("abort", abortFromParent, { once: true });

  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (timedOut) {
      throw new AttackError(
        "PROVIDER_TIMEOUT",
        "음성 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.",
        true,
        504,
        { cause: error instanceof Error ? error : undefined },
      );
    }
    if (parentSignal.aborted) {
      throw new AttackError(
        "REQUEST_CANCELLED",
        "요청이 취소되었습니다.",
        true,
        499,
      );
    }
    throw new AttackError(
      "PROVIDER_FAILED",
      "음성 생성 서비스에 연결하지 못했습니다.",
      true,
      502,
      { cause: error instanceof Error ? error : undefined },
    );
  } finally {
    clearTimeout(timer);
    parentSignal.removeEventListener("abort", abortFromParent);
  }
}

export class FishAudioProvider implements VoiceCloneProvider {
  readonly name = "fish-audio" as const;

  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly model: string;

  constructor() {
    const apiKey = process.env.FISH_AUDIO_API_KEY?.trim();
    if (!apiKey) {
      throw new AttackError(
        "PROVIDER_NOT_CONFIGURED",
        "Fish Audio API 키가 설정되지 않았습니다.",
        false,
        503,
      );
    }
    this.apiKey = apiKey;
    this.baseUrl = (process.env.FISH_AUDIO_BASE_URL ?? DEFAULT_BASE_URL).replace(
      /\/$/,
      "",
    );
    this.model = process.env.FISH_AUDIO_MODEL?.trim() || DEFAULT_MODEL;
  }

  private authorization(): string {
    return `Bearer ${this.apiKey}`;
  }

  async createClone({
    audio,
    referenceText,
    requestId,
    signal,
  }: Parameters<VoiceCloneProvider["createClone"]>[0]): Promise<CloneReference> {
    const body = new FormData();
    body.append("type", "tts");
    body.append("title", `voiceshield-${requestId}`);
    body.append("train_mode", "fast");
    body.append("visibility", "private");
    body.append(
      "voices",
      new Blob([audio.bytes.slice().buffer], { type: audio.mimeType }),
      audio.filename,
    );
    body.append("texts", referenceText);
    body.append("enhance_audio_quality", "true");
    body.append("generate_sample", "false");

    const response = await fetchWithTimeout(
      `${this.baseUrl}/model`,
      {
        method: "POST",
        headers: { Authorization: this.authorization() },
        body,
        cache: "no-store",
      },
      signal,
    );

    if (!response.ok) {
      throw mapProviderError(response.status, await safeErrorDetail(response));
    }

    const data = (await response.json()) as ModelResponse;
    if (typeof data._id !== "string" || !isCloneState(data.state)) {
      throw new AttackError(
        "PROVIDER_FAILED",
        "음성 생성 서비스의 응답 형식이 올바르지 않습니다.",
        true,
        502,
      );
    }

    return { id: data._id, state: data.state };
  }

  async waitUntilReady({
    clone,
    signal,
  }: Parameters<VoiceCloneProvider["waitUntilReady"]>[0]): Promise<CloneReference> {
    if (clone.state === "created" || clone.state === "trained") return clone;
    if (clone.state === "failed") {
      throw new AttackError(
        "PROVIDER_REJECTED",
        "참조 음성으로 Voice Clone을 준비하지 못했습니다.",
        true,
        502,
      );
    }

    for (let attempt = 0; attempt < MODEL_POLL_LIMIT; attempt += 1) {
      await delay(MODEL_POLL_INTERVAL_MS, undefined, { signal });
      const response = await fetchWithTimeout(
        `${this.baseUrl}/model/${encodeURIComponent(clone.id)}`,
        {
          headers: { Authorization: this.authorization() },
          cache: "no-store",
        },
        signal,
      );
      if (!response.ok) {
        throw mapProviderError(response.status, await safeErrorDetail(response));
      }
      const data = (await response.json()) as ModelResponse;
      if (typeof data._id !== "string" || !isCloneState(data.state)) {
        throw new AttackError(
          "PROVIDER_FAILED",
          "Voice Clone 상태를 확인하지 못했습니다.",
          true,
          502,
        );
      }
      if (data.state === "created" || data.state === "trained") {
        return { id: data._id, state: data.state };
      }
      if (data.state === "failed") {
        throw new AttackError(
          "PROVIDER_REJECTED",
          "참조 음성으로 Voice Clone을 준비하지 못했습니다.",
          true,
          502,
        );
      }
    }

    throw new AttackError(
      "PROVIDER_TIMEOUT",
      "Voice Clone 준비 시간이 초과되었습니다.",
      true,
      504,
    );
  }

  async generateSpeech({
    clone,
    text,
    signal,
  }: Parameters<VoiceCloneProvider["generateSpeech"]>[0]): Promise<GeneratedAudio> {
    const response = await fetchWithTimeout(
      `${this.baseUrl}/v1/tts`,
      {
        method: "POST",
        headers: {
          Authorization: this.authorization(),
          "Content-Type": "application/json",
          model: this.model,
        },
        body: JSON.stringify({
          text,
          reference_id: clone.id,
          format: "mp3",
          mp3_bitrate: 128,
          normalize: true,
          latency: "normal",
        }),
        cache: "no-store",
      },
      signal,
    );

    if (!response.ok) {
      throw mapProviderError(response.status, await safeErrorDetail(response));
    }

    const declaredLength = Number(response.headers.get("content-length"));
    if (
      Number.isFinite(declaredLength) &&
      declaredLength > MAX_GENERATED_AUDIO_BYTES
    ) {
      throw new AttackError(
        "PROVIDER_FAILED",
        "생성된 음성 파일이 허용 크기를 초과했습니다.",
        false,
        502,
      );
    }

    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.byteLength === 0 || bytes.byteLength > MAX_GENERATED_AUDIO_BYTES) {
      throw new AttackError(
        "PROVIDER_FAILED",
        "생성된 음성 파일을 확인할 수 없습니다.",
        true,
        502,
      );
    }

    const responseType = response.headers.get("content-type")?.split(";")[0];
    return {
      bytes,
      mimeType:
        responseType?.startsWith("audio/") === true
          ? responseType
          : "audio/mpeg",
    };
  }

  async deleteClone({
    clone,
    signal,
  }: Parameters<VoiceCloneProvider["deleteClone"]>[0]): Promise<void> {
    const response = await fetchWithTimeout(
      `${this.baseUrl}/model/${encodeURIComponent(clone.id)}`,
      {
        method: "DELETE",
        headers: { Authorization: this.authorization() },
        cache: "no-store",
      },
      signal,
    );

    if (!response.ok && response.status !== 404) {
      throw mapProviderError(response.status, await safeErrorDetail(response));
    }
  }
}

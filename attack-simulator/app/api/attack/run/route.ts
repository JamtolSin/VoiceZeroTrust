import { randomUUID } from "node:crypto";

import {
  CONSENT_VERSION,
  isSafePhraseId,
  SAFE_PHRASES,
} from "@/lib/attack/constants";
import {
  AttackError,
  toAttackError,
  toErrorPayload,
} from "@/lib/attack/errors";
import { runVoiceCloneAttack } from "@/lib/attack/runner";
import { encodeStreamEvent } from "@/lib/attack/stream";
import { validatePcm16Wav } from "@/lib/audio/wav";
import {
  checkRateLimit,
  getAnonymousClientKey,
} from "@/lib/security/rate-limit";
import { createVoiceProvider } from "@/lib/voice/provider-factory";
import type { AttackStreamEvent } from "@/types/attack";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 180;

function responseHeaders(requestId: string): HeadersInit {
  return {
    "Cache-Control": "no-store, max-age=0",
    "Content-Type": "application/x-ndjson; charset=utf-8",
    "X-Content-Type-Options": "nosniff",
    "X-Request-Id": requestId,
  };
}

function singleEventResponse(
  event: AttackStreamEvent,
  requestId: string,
  status: number,
  additionalHeaders?: HeadersInit,
): Response {
  return new Response(encodeStreamEvent(event).slice().buffer, {
    status,
    headers: { ...responseHeaders(requestId), ...additionalHeaders },
  });
}

function assertSameOrigin(request: Request): void {
  if (request.headers.get("sec-fetch-site") === "cross-site") {
    throw new AttackError(
      "INVALID_REQUEST",
      "허용되지 않은 요청 출처입니다.",
      false,
      403,
    );
  }

  const origin = request.headers.get("origin");
  if (!origin) return;

  const requestHost =
    request.headers.get("x-forwarded-host") ?? new URL(request.url).host;
  if (new URL(origin).host !== requestHost) {
    throw new AttackError(
      "INVALID_REQUEST",
      "허용되지 않은 요청 출처입니다.",
      false,
      403,
    );
  }
}

async function parseForm(request: Request): Promise<{
  bytes: Uint8Array;
  filename: string;
  phrase: string;
}> {
  let form: FormData;
  try {
    form = await request.formData();
  } catch (error) {
    throw new AttackError(
      "INVALID_REQUEST",
      "요청 형식을 읽을 수 없습니다.",
      false,
      400,
      { cause: error instanceof Error ? error : undefined },
    );
  }

  if (
    form.get("consentOwnVoice") !== "true" ||
    form.get("consentProcessing") !== "true" ||
    form.get("consentVersion") !== CONSENT_VERSION
  ) {
    throw new AttackError(
      "CONSENT_REQUIRED",
      "본인 음성과 외부 음성 처리에 대한 동의가 필요합니다.",
      false,
      400,
    );
  }

  const phraseId = form.get("phraseId");
  if (!isSafePhraseId(phraseId)) {
    throw new AttackError(
      "PHRASE_NOT_ALLOWED",
      "허용된 안전 문장을 선택해주세요.",
      false,
      400,
    );
  }

  const audio = form.get("audio");
  if (!(audio instanceof File) || audio.size === 0) {
    throw new AttackError(
      "AUDIO_REQUIRED",
      "10초 녹음 파일이 필요합니다.",
      true,
      400,
    );
  }
  if (audio.type !== "audio/wav" && audio.type !== "audio/x-wav") {
    throw new AttackError(
      "AUDIO_FORMAT_INVALID",
      "브라우저에서 생성한 WAV 녹음만 사용할 수 있습니다.",
      true,
      415,
    );
  }

  return {
    bytes: new Uint8Array(await audio.arrayBuffer()),
    filename: "voice-sample.wav",
    phrase: SAFE_PHRASES[phraseId],
  };
}

export async function POST(request: Request): Promise<Response> {
  const requestId = randomUUID();

  try {
    assertSameOrigin(request);
    const rateLimit = checkRateLimit(getAnonymousClientKey(request));
    if (!rateLimit.allowed) {
      const error = new AttackError(
        "RATE_LIMITED",
        "테스트 횟수 제한에 도달했습니다. 잠시 후 다시 시도해주세요.",
        true,
        429,
      );
      return singleEventResponse(
        { type: "error", error: toErrorPayload(error, requestId) },
        requestId,
        error.status,
        { "Retry-After": String(rateLimit.retryAfterSeconds) },
      );
    }

    const form = await parseForm(request);
    const jobController = new AbortController();
    const abortJob = () => jobController.abort(request.signal.reason);
    request.signal.addEventListener("abort", abortJob, { once: true });
    let streamCancelled = false;

    const stream = new ReadableStream<Uint8Array>({
      async start(controller) {
        const send = (event: AttackStreamEvent) => {
          if (streamCancelled) return;
          try {
            controller.enqueue(encodeStreamEvent(event));
          } catch {
            streamCancelled = true;
            jobController.abort();
          }
        };
        const startedAt = performance.now();

        try {
          send({
            type: "status",
            stage: "validating",
            elapsedMs: 0,
            message: "녹음 길이와 입력 음량을 확인하고 있습니다.",
          });
          const validationStartedAt = performance.now();
          const audio = validatePcm16Wav(form.bytes, form.filename);
          const validationMs = performance.now() - validationStartedAt;
          const provider = createVoiceProvider();
          const result = await runVoiceCloneAttack({
            audio,
            phrase: form.phrase,
            requestId,
            validationMs,
            provider,
            signal: jobController.signal,
            onStage(stage, elapsedMs, message) {
              send({ type: "status", stage, elapsedMs, message });
            },
          });

          send({
            type: "complete",
            provider: result.provider,
            audio: {
              mimeType: result.audio.mimeType,
              base64: Buffer.from(result.audio.bytes).toString("base64"),
            },
            timings: {
              ...result.timings,
              totalMs: performance.now() - startedAt,
            },
            cleanupCompleted: result.cleanupCompleted,
          });
        } catch (error) {
          const attackError = toAttackError(error);
          if (attackError.status >= 500) {
            console.error("Attack request failed", {
              requestId,
              code: attackError.code,
              cause:
                attackError.cause instanceof Error
                  ? attackError.cause.message.slice(0, 200)
                  : undefined,
            });
          }
          send({ type: "error", error: toErrorPayload(attackError, requestId) });
        } finally {
          request.signal.removeEventListener("abort", abortJob);
          if (!streamCancelled) controller.close();
        }
      },
      cancel() {
        streamCancelled = true;
        jobController.abort();
      },
    });

    return new Response(stream, { headers: responseHeaders(requestId) });
  } catch (error) {
    const attackError = toAttackError(error);
    return singleEventResponse(
      { type: "error", error: toErrorPayload(attackError, requestId) },
      requestId,
      attackError.status,
    );
  }
}

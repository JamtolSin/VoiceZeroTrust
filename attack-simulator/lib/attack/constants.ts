export const CONSENT_VERSION = "2026-09-16.v1";

export const RECORDING_TARGET_MS = 10_000;
export const RECORDING_MIN_MS = 9_500;
export const RECORDING_MAX_MS = 10_500;

export const MAX_AUDIO_BYTES = 400_000;
export const MIN_AUDIO_RMS = 0.008;
export const MIN_AUDIO_PEAK = 0.025;

export const REFERENCE_PROMPT =
  "오늘은 맑은 하늘 아래 작은 새들이 노래하고, 따뜻한 바람이 천천히 창문을 스쳐 지나갑니다.";

export const SAFE_PHRASES = {
  ai_disclosure: "이 음성은 인공지능이 생성한 음성입니다.",
  never_spoken: "저는 이 문장을 실제로 말한 적이 없습니다.",
  ten_seconds: "단 10초의 음성만으로 새로운 문장이 만들어졌습니다.",
} as const;

export type SafePhraseId = keyof typeof SAFE_PHRASES;

export function isSafePhraseId(value: unknown): value is SafePhraseId {
  return typeof value === "string" && value in SAFE_PHRASES;
}

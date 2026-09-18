export const ATTACK_STAGES = [
  "validating",
  "cloning",
  "generating",
  "cleaning",
] as const;

export type AttackStage = (typeof ATTACK_STAGES)[number];

export type AttackErrorCode =
  | "INVALID_REQUEST"
  | "CONSENT_REQUIRED"
  | "PHRASE_NOT_ALLOWED"
  | "AUDIO_REQUIRED"
  | "AUDIO_TOO_LARGE"
  | "AUDIO_FORMAT_INVALID"
  | "AUDIO_DURATION_INVALID"
  | "AUDIO_TOO_QUIET"
  | "RATE_LIMITED"
  | "PROVIDER_NOT_CONFIGURED"
  | "PROVIDER_AUTH_FAILED"
  | "PROVIDER_RATE_LIMITED"
  | "PROVIDER_REJECTED"
  | "PROVIDER_TIMEOUT"
  | "PROVIDER_FAILED"
  | "CLEANUP_FAILED"
  | "REQUEST_CANCELLED"
  | "INTERNAL_ERROR";

export type AttackErrorPayload = {
  code: AttackErrorCode;
  message: string;
  retryable: boolean;
  requestId: string;
};

export type AttackTimings = {
  recordingMs: number;
  validationMs: number;
  cloneMs: number;
  generationMs: number;
  cleanupMs: number;
  totalMs: number;
};

export type AttackStreamEvent =
  | {
      type: "status";
      stage: AttackStage;
      elapsedMs: number;
      message: string;
    }
  | {
      type: "complete";
      provider: "fish-audio" | "mock";
      audio: {
        mimeType: string;
        base64: string;
      };
      timings: AttackTimings;
      cleanupCompleted: boolean;
    }
  | {
      type: "error";
      error: AttackErrorPayload;
    };

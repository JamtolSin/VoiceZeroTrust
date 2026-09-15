import type { AttackErrorCode, AttackErrorPayload } from "@/types/attack";

export class AttackError extends Error {
  constructor(
    readonly code: AttackErrorCode,
    message: string,
    readonly retryable = false,
    readonly status = 400,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "AttackError";
  }
}

export function toAttackError(error: unknown): AttackError {
  if (error instanceof AttackError) {
    return error;
  }

  if (error instanceof DOMException && error.name === "AbortError") {
    return new AttackError(
      "REQUEST_CANCELLED",
      "요청이 취소되었습니다. 다시 시도해주세요.",
      true,
      499,
      { cause: error },
    );
  }

  return new AttackError(
    "INTERNAL_ERROR",
    "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
    true,
    500,
    { cause: error instanceof Error ? error : undefined },
  );
}

export function toErrorPayload(
  error: unknown,
  requestId: string,
): AttackErrorPayload {
  const attackError = toAttackError(error);

  return {
    code: attackError.code,
    message: attackError.message,
    retryable: attackError.retryable,
    requestId,
  };
}

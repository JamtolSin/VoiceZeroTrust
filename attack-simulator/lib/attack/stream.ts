import type { AttackStreamEvent } from "@/types/attack";

const encoder = new TextEncoder();

export function encodeStreamEvent(event: AttackStreamEvent): Uint8Array {
  return encoder.encode(`${JSON.stringify(event)}\n`);
}

export async function consumeAttackStream(
  response: Response,
  onEvent: (event: AttackStreamEvent) => void,
): Promise<void> {
  if (!response.body) {
    throw new Error("서버 응답 스트림을 읽을 수 없습니다.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.trim()) continue;
      onEvent(JSON.parse(line) as AttackStreamEvent);
    }

    if (done) break;
  }

  if (buffer.trim()) {
    onEvent(JSON.parse(buffer) as AttackStreamEvent);
  }
}

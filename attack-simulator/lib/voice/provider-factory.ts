import { AttackError } from "@/lib/attack/errors";
import { FishAudioProvider } from "@/lib/voice/fish-audio-provider";
import { MockVoiceProvider } from "@/lib/voice/mock-provider";
import type { VoiceCloneProvider } from "@/lib/voice/provider";

export function createVoiceProvider(): VoiceCloneProvider {
  const provider = process.env.VOICE_PROVIDER?.trim() || "mock";

  if (provider === "fish-audio") return new FishAudioProvider();

  if (provider === "mock") {
    if (
      process.env.NODE_ENV === "production" &&
      process.env.ALLOW_MOCK_PROVIDER !== "true"
    ) {
      throw new AttackError(
        "PROVIDER_NOT_CONFIGURED",
        "Production 환경에서는 실제 Voice Provider를 설정해야 합니다.",
        false,
        503,
      );
    }
    return new MockVoiceProvider();
  }

  throw new AttackError(
    "PROVIDER_NOT_CONFIGURED",
    `지원하지 않는 Voice Provider 설정입니다: ${provider}`,
    false,
    503,
  );
}

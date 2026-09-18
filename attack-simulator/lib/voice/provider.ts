import type { ValidatedAudio } from "@/lib/audio/wav";

export type VoiceProviderName = "fish-audio" | "mock";

export type CloneState = "created" | "training" | "trained" | "failed";

export type CloneReference = {
  id: string;
  state: CloneState;
};

export type GeneratedAudio = {
  bytes: Uint8Array;
  mimeType: string;
};

export interface VoiceCloneProvider {
  readonly name: VoiceProviderName;

  createClone(input: {
    audio: ValidatedAudio;
    referenceText: string;
    requestId: string;
    signal: AbortSignal;
  }): Promise<CloneReference>;

  waitUntilReady(input: {
    clone: CloneReference;
    signal: AbortSignal;
  }): Promise<CloneReference>;

  generateSpeech(input: {
    clone: CloneReference;
    text: string;
    requestId: string;
    signal: AbortSignal;
  }): Promise<GeneratedAudio>;

  deleteClone(input: {
    clone: CloneReference;
    signal: AbortSignal;
  }): Promise<void>;
}

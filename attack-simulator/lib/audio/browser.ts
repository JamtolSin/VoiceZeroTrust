import { encodePcm16Wav } from "@/lib/audio/wav";

const OUTPUT_SAMPLE_RATE = 16_000;

export type BrowserAudioResult = {
  blob: Blob;
  durationMs: number;
};

export async function convertRecordingToWav(
  recording: Blob,
): Promise<BrowserAudioResult> {
  const sourceBytes = await recording.arrayBuffer();
  const audioContext = new AudioContext();

  try {
    const decoded = await audioContext.decodeAudioData(sourceBytes.slice(0));
    const durationMs = decoded.duration * 1000;
    const outputFrames = Math.max(
      1,
      Math.round(decoded.duration * OUTPUT_SAMPLE_RATE),
    );
    const offline = new OfflineAudioContext(
      1,
      outputFrames,
      OUTPUT_SAMPLE_RATE,
    );
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start(0);

    const rendered = await offline.startRendering();
    const wav = encodePcm16Wav(
      rendered.getChannelData(0),
      OUTPUT_SAMPLE_RATE,
    );

    return {
      blob: new Blob([wav.slice().buffer], { type: "audio/wav" }),
      durationMs,
    };
  } finally {
    await audioContext.close();
  }
}

export function selectRecordingMimeType(): string | undefined {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
  ];

  return candidates.find((type) => MediaRecorder.isTypeSupported(type));
}

import { AttackError } from "@/lib/attack/errors";
import {
  MAX_AUDIO_BYTES,
  MIN_AUDIO_PEAK,
  MIN_AUDIO_RMS,
  RECORDING_MAX_MS,
  RECORDING_MIN_MS,
} from "@/lib/attack/constants";

const PCM_FORMAT = 1;
const PCM_BITS = 16;
const EXPECTED_CHANNELS = 1;
const EXPECTED_SAMPLE_RATE = 16_000;
const WAV_HEADER_BYTES = 44;

export type ValidatedAudio = {
  bytes: Uint8Array;
  mimeType: "audio/wav";
  filename: string;
  durationMs: number;
  sampleRate: number;
  channels: number;
  rms: number;
  peak: number;
};

type WavMetadata = {
  audioFormat: number;
  channels: number;
  sampleRate: number;
  bitsPerSample: number;
  dataOffset: number;
  dataSize: number;
};

function readAscii(bytes: Uint8Array, offset: number, length: number): string {
  return String.fromCharCode(...bytes.subarray(offset, offset + length));
}

function parseMetadata(bytes: Uint8Array): WavMetadata {
  if (
    bytes.byteLength < WAV_HEADER_BYTES ||
    readAscii(bytes, 0, 4) !== "RIFF" ||
    readAscii(bytes, 8, 4) !== "WAVE"
  ) {
    throw new AttackError(
      "AUDIO_FORMAT_INVALID",
      "지원하지 않는 오디오 형식입니다. 다시 녹음해주세요.",
    );
  }

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 12;
  let format: Omit<WavMetadata, "dataOffset" | "dataSize"> | undefined;
  let dataOffset = -1;
  let dataSize = -1;

  while (offset + 8 <= bytes.byteLength) {
    const chunkId = readAscii(bytes, offset, 4);
    const chunkSize = view.getUint32(offset + 4, true);
    const contentOffset = offset + 8;
    const contentEnd = contentOffset + chunkSize;

    if (contentEnd > bytes.byteLength) {
      throw new AttackError(
        "AUDIO_FORMAT_INVALID",
        "오디오 파일이 손상되었습니다. 다시 녹음해주세요.",
      );
    }

    if (chunkId === "fmt ") {
      if (chunkSize < 16) {
        throw new AttackError(
          "AUDIO_FORMAT_INVALID",
          "오디오 형식 정보를 읽을 수 없습니다.",
        );
      }

      format = {
        audioFormat: view.getUint16(contentOffset, true),
        channels: view.getUint16(contentOffset + 2, true),
        sampleRate: view.getUint32(contentOffset + 4, true),
        bitsPerSample: view.getUint16(contentOffset + 14, true),
      };
    }

    if (chunkId === "data") {
      dataOffset = contentOffset;
      dataSize = chunkSize;
    }

    offset = contentEnd + (chunkSize % 2);
  }

  if (!format || dataOffset < 0 || dataSize <= 0) {
    throw new AttackError(
      "AUDIO_FORMAT_INVALID",
      "오디오 데이터를 읽을 수 없습니다. 다시 녹음해주세요.",
    );
  }

  return { ...format, dataOffset, dataSize };
}

export function encodePcm16Wav(
  samples: Float32Array,
  sampleRate = EXPECTED_SAMPLE_RATE,
): Uint8Array {
  const buffer = new ArrayBuffer(WAV_HEADER_BYTES + samples.length * 2);
  const view = new DataView(buffer);

  const writeAscii = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };

  writeAscii(0, "RIFF");
  view.setUint32(4, buffer.byteLength - 8, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, PCM_FORMAT, true);
  view.setUint16(22, EXPECTED_CHANNELS, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, PCM_BITS, true);
  writeAscii(36, "data");
  view.setUint32(40, samples.length * 2, true);

  for (let index = 0; index < samples.length; index += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[index]));
    const pcm = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
    view.setInt16(WAV_HEADER_BYTES + index * 2, Math.round(pcm), true);
  }

  return new Uint8Array(buffer);
}

export function validatePcm16Wav(
  bytes: Uint8Array,
  filename = "voice-sample.wav",
): ValidatedAudio {
  if (bytes.byteLength > MAX_AUDIO_BYTES) {
    throw new AttackError(
      "AUDIO_TOO_LARGE",
      "녹음 파일이 허용 크기를 초과했습니다. 다시 녹음해주세요.",
    );
  }

  const metadata = parseMetadata(bytes);

  if (
    metadata.audioFormat !== PCM_FORMAT ||
    metadata.bitsPerSample !== PCM_BITS ||
    metadata.channels !== EXPECTED_CHANNELS ||
    metadata.sampleRate !== EXPECTED_SAMPLE_RATE ||
    metadata.dataSize % 2 !== 0
  ) {
    throw new AttackError(
      "AUDIO_FORMAT_INVALID",
      "16kHz 모노 PCM WAV 형식만 사용할 수 있습니다. 다시 녹음해주세요.",
    );
  }

  const sampleCount = metadata.dataSize / 2;
  const durationMs = (sampleCount / metadata.sampleRate) * 1000;

  if (durationMs < RECORDING_MIN_MS || durationMs > RECORDING_MAX_MS) {
    throw new AttackError(
      "AUDIO_DURATION_INVALID",
      `녹음 길이는 10초여야 합니다. 현재 ${(
        durationMs / 1000
      ).toFixed(1)}초입니다.`,
    );
  }

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let sumSquares = 0;
  let peak = 0;

  for (let offset = 0; offset < metadata.dataSize; offset += 2) {
    const value = view.getInt16(metadata.dataOffset + offset, true) / 0x8000;
    sumSquares += value * value;
    peak = Math.max(peak, Math.abs(value));
  }

  const rms = Math.sqrt(sumSquares / sampleCount);
  if (rms < MIN_AUDIO_RMS || peak < MIN_AUDIO_PEAK) {
    throw new AttackError(
      "AUDIO_TOO_QUIET",
      "목소리가 충분히 녹음되지 않았습니다. 조용한 환경에서 다시 녹음해주세요.",
      true,
    );
  }

  return {
    bytes,
    mimeType: "audio/wav",
    filename,
    durationMs,
    sampleRate: metadata.sampleRate,
    channels: metadata.channels,
    rms,
    peak,
  };
}

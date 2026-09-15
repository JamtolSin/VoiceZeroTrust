"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  convertRecordingToWav,
  selectRecordingMimeType,
  type BrowserAudioResult,
} from "@/lib/audio/browser";
import { RECORDING_TARGET_MS } from "@/lib/attack/constants";

export type RecorderStatus =
  | "idle"
  | "requesting"
  | "recording"
  | "processing"
  | "ready"
  | "error";

type VoiceRecorderState = {
  status: RecorderStatus;
  elapsedMs: number;
  level: number;
  audio: BrowserAudioResult | null;
  error: string | null;
};

const INITIAL_STATE: VoiceRecorderState = {
  status: "idle",
  elapsedMs: 0,
  level: 0,
  audio: null,
  error: null,
};

function stopTracks(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}

export function useVoiceRecorder() {
  const [state, setState] = useState<VoiceRecorderState>(INITIAL_STATE);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tickTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const animationRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);

  const cleanupCapture = useCallback(() => {
    if (stopTimerRef.current) clearTimeout(stopTimerRef.current);
    if (tickTimerRef.current) clearInterval(tickTimerRef.current);
    if (animationRef.current) cancelAnimationFrame(animationRef.current);
    stopTimerRef.current = null;
    tickTimerRef.current = null;
    animationRef.current = null;
    stopTracks(streamRef.current);
    streamRef.current = null;
    recorderRef.current = null;
  }, []);

  const reset = useCallback(() => {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }
    cleanupCapture();
    setState(INITIAL_STATE);
  }, [cleanupCapture]);

  const start = useCallback(async () => {
    cleanupCapture();
    setState({ ...INITIAL_STATE, status: "requesting" });

    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        throw new Error("이 브라우저는 마이크 녹음을 지원하지 않습니다.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const mimeType = selectRecordingMimeType();
      const recorder = new MediaRecorder(
        stream,
        mimeType ? { mimeType } : undefined,
      );
      recorderRef.current = recorder;
      const chunks: Blob[] = [];

      const meterContext = new AudioContext();
      const source = meterContext.createMediaStreamSource(stream);
      const analyser = meterContext.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      const levels = new Uint8Array(analyser.fftSize);

      const updateLevel = () => {
        analyser.getByteTimeDomainData(levels);
        let sumSquares = 0;
        for (const value of levels) {
          const normalized = (value - 128) / 128;
          sumSquares += normalized * normalized;
        }
        const rms = Math.sqrt(sumSquares / levels.length);
        setState((current) => ({
          ...current,
          level: Math.min(1, rms * 6),
        }));
        animationRef.current = requestAnimationFrame(updateLevel);
      };

      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      });

      recorder.addEventListener(
        "stop",
        async () => {
          if (tickTimerRef.current) clearInterval(tickTimerRef.current);
          if (animationRef.current) cancelAnimationFrame(animationRef.current);
          stopTracks(stream);
          await meterContext.close();
          setState((current) => ({
            ...current,
            status: "processing",
            elapsedMs: RECORDING_TARGET_MS,
            level: 0,
          }));

          try {
            const recording = new Blob(chunks, {
              type: recorder.mimeType || "audio/webm",
            });
            if (recording.size === 0) {
              throw new Error("녹음 파일이 생성되지 않았습니다.");
            }
            const audio = await convertRecordingToWav(recording);
            setState((current) => ({
              ...current,
              status: "ready",
              audio,
              error: null,
            }));
          } catch (error) {
            setState((current) => ({
              ...current,
              status: "error",
              audio: null,
              error:
                error instanceof Error
                  ? error.message
                  : "녹음을 처리하지 못했습니다.",
            }));
          }
        },
        { once: true },
      );

      recorder.start(250);
      startedAtRef.current = performance.now();
      setState({ ...INITIAL_STATE, status: "recording" });
      updateLevel();

      tickTimerRef.current = setInterval(() => {
        const elapsed = Math.min(
          RECORDING_TARGET_MS,
          performance.now() - startedAtRef.current,
        );
        setState((current) => ({ ...current, elapsedMs: elapsed }));
      }, 50);

      stopTimerRef.current = setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, RECORDING_TARGET_MS);
    } catch (error) {
      cleanupCapture();
      const denied =
        error instanceof DOMException && error.name === "NotAllowedError";
      setState({
        ...INITIAL_STATE,
        status: "error",
        error: denied
          ? "마이크 권한이 거부되었습니다. 브라우저 설정에서 권한을 허용해주세요."
          : error instanceof Error
            ? error.message
            : "마이크를 시작하지 못했습니다.",
      });
    }
  }, [cleanupCapture]);

  useEffect(() => cleanupCapture, [cleanupCapture]);

  return { ...state, start, reset };
}

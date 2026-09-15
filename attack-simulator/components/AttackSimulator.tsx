"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AudioPlayer } from "@/components/AudioPlayer";
import { LevelMeter } from "@/components/LevelMeter";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import {
  CONSENT_VERSION,
  RECORDING_TARGET_MS,
  REFERENCE_PROMPT,
  SAFE_PHRASES,
  type SafePhraseId,
} from "@/lib/attack/constants";
import { consumeAttackStream } from "@/lib/attack/stream";
import type {
  AttackErrorPayload,
  AttackStage,
  AttackStreamEvent,
  AttackTimings,
} from "@/types/attack";

type View =
  | "intro"
  | "consent"
  | "record"
  | "phrase"
  | "processing"
  | "result"
  | "error";

type ResultState = {
  provider: "fish-audio" | "mock";
  generatedUrl: string;
  timings: AttackTimings;
  cleanupCompleted: boolean;
};

const STAGE_ORDER: Array<{
  id: AttackStage;
  number: string;
  label: string;
}> = [
  { id: "validating", number: "01", label: "VOICE SAMPLE ACQUIRED" },
  { id: "cloning", number: "02", label: "VOICE CLONING" },
  { id: "generating", number: "03", label: "NEW SPEECH GENERATION" },
  { id: "cleaning", number: "04", label: "PRIVACY CLEANUP" },
];

function formatDuration(milliseconds: number): string {
  return `${(milliseconds / 1000).toFixed(1)} sec`;
}

function decodeBase64Audio(base64: string, mimeType: string): Blob {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Blob([bytes], { type: mimeType });
}

function useBlobUrl(blob: Blob | null): string {
  const url = useMemo(() => (blob ? URL.createObjectURL(blob) : ""), [blob]);

  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );

  return url;
}

export function AttackSimulator() {
  const [view, setView] = useState<View>("intro");
  const [ownVoiceConsent, setOwnVoiceConsent] = useState(false);
  const [processingConsent, setProcessingConsent] = useState(false);
  const [phraseId, setPhraseId] = useState<SafePhraseId>("never_spoken");
  const [activeStage, setActiveStage] = useState<AttackStage>("validating");
  const [stageMessage, setStageMessage] = useState("");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [result, setResult] = useState<ResultState | null>(null);
  const [error, setError] = useState<AttackErrorPayload | null>(null);
  const requestStartedAtRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const recorder = useVoiceRecorder();
  const originalUrl = useBlobUrl(recorder.audio?.blob ?? null);

  const disposeResult = useCallback(() => {
    setResult((current) => {
      if (current) URL.revokeObjectURL(current.generatedUrl);
      return null;
    });
  }, []);

  useEffect(() => {
    if (view !== "processing") return;
    const timer = setInterval(() => {
      setElapsedMs(performance.now() - requestStartedAtRef.current);
    }, 100);
    return () => clearInterval(timer);
  }, [view]);

  useEffect(
    () => () => {
      requestControllerRef.current?.abort();
    },
    [],
  );

  const resetAll = useCallback(() => {
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;
    disposeResult();
    recorder.reset();
    setOwnVoiceConsent(false);
    setProcessingConsent(false);
    setPhraseId("never_spoken");
    setActiveStage("validating");
    setStageMessage("");
    setElapsedMs(0);
    setError(null);
    setView("intro");
  }, [disposeResult, recorder]);

  const runAttack = useCallback(async () => {
    if (!recorder.audio || !ownVoiceConsent || !processingConsent) return;

    const controller = new AbortController();
    requestControllerRef.current = controller;
    requestStartedAtRef.current = performance.now();
    setElapsedMs(0);
    setError(null);
    setActiveStage("validating");
    setStageMessage("녹음 파일을 안전하게 확인하고 있습니다.");
    setView("processing");

    const form = new FormData();
    form.append("audio", recorder.audio.blob, "voice-sample.wav");
    form.append("phraseId", phraseId);
    form.append("consentOwnVoice", String(ownVoiceConsent));
    form.append("consentProcessing", String(processingConsent));
    form.append("consentVersion", CONSENT_VERSION);

    let terminalEvent: AttackStreamEvent | null = null;

    try {
      const response = await fetch("/api/attack/run", {
        method: "POST",
        body: form,
        signal: controller.signal,
      });

      await consumeAttackStream(response, (event) => {
        if (event.type === "status") {
          setActiveStage(event.stage);
          setStageMessage(event.message);
          return;
        }
        terminalEvent = event;
      });

      if (!terminalEvent) {
        throw new Error("서버가 처리 결과를 반환하지 않았습니다.");
      }

      const finalEvent = terminalEvent as Exclude<
        AttackStreamEvent,
        { type: "status" }
      >;
      if (finalEvent.type === "error") {
        setError(finalEvent.error);
        setView("error");
        return;
      }

      const generatedBlob = decodeBase64Audio(
        finalEvent.audio.base64,
        finalEvent.audio.mimeType,
      );
      disposeResult();
      setResult({
        provider: finalEvent.provider,
        generatedUrl: URL.createObjectURL(generatedBlob),
        timings: finalEvent.timings,
        cleanupCompleted: finalEvent.cleanupCompleted,
      });
      setView("result");
    } catch (caught) {
      if (controller.signal.aborted) {
        setError({
          code: "REQUEST_CANCELLED",
          message: "요청이 취소되었습니다. 녹음은 브라우저에 남아 있습니다.",
          retryable: true,
          requestId: "local",
        });
      } else {
        setError({
          code: "INTERNAL_ERROR",
          message:
            caught instanceof Error
              ? caught.message
              : "처리 결과를 읽지 못했습니다.",
          retryable: true,
          requestId: "local",
        });
      }
      setView("error");
    } finally {
      requestControllerRef.current = null;
    }
  }, [
    disposeResult,
    ownVoiceConsent,
    phraseId,
    processingConsent,
    recorder.audio,
  ]);

  const cancelRequest = useCallback(() => {
    requestControllerRef.current?.abort();
  }, []);

  const completedStageIndex = useMemo(
    () => STAGE_ORDER.findIndex((stage) => stage.id === activeStage),
    [activeStage],
  );

  return (
    <div id="top" className="simulator">
      {view === "intro" && (
        <section className="hero panel-enter" aria-labelledby="hero-title">
          <div className="eyebrow">
            <span className="eyebrow-line" /> ATTACK SIMULATION / 10 SEC
          </div>
          <h1 id="hero-title">
            목소리를 복제하는 데
            <br />
            <span>얼마나 필요할까요?</span>
          </h1>
          <p className="hero-copy">
            직접 녹음한 본인 음성 10초로 Voice Cloning의 위험을 확인합니다.
            생성 문장은 안전한 고정 문구로 제한됩니다.
          </p>

          <div className="impact-stat" aria-label="10초 음성 샘플">
            <span className="impact-number">10</span>
            <span>
              <strong>SECONDS</strong>
              <small>ONE VOICE SAMPLE</small>
            </span>
          </div>

          <button className="primary-button" onClick={() => setView("consent")}>
            공격 시뮬레이션 시작
            <span aria-hidden="true">→</span>
          </button>

          <div className="trust-row">
            <span>직접 녹음만 허용</span>
            <span>고정 안전 문장</span>
            <span>처리 후 Clone 삭제</span>
          </div>
        </section>
      )}

      {view === "consent" && (
        <section className="content-panel panel-enter" aria-labelledby="consent-title">
          <StepHeader
            step="01 / 04"
            title="본인 음성 사용 확인"
            description="두 항목을 모두 확인해야 녹음을 시작할 수 있습니다."
          />

          <div className="consent-list">
            <label className={ownVoiceConsent ? "consent-card checked" : "consent-card"}>
              <input
                type="checkbox"
                checked={ownVoiceConsent}
                onChange={(event) => setOwnVoiceConsent(event.target.checked)}
              />
              <span className="check-box" aria-hidden="true">✓</span>
              <span>
                <strong>현재 녹음할 음성은 제 본인의 음성입니다.</strong>
                <small>타인의 음성, 저장된 파일 또는 외부 URL은 사용할 수 없습니다.</small>
              </span>
            </label>

            <label className={processingConsent ? "consent-card checked" : "consent-card"}>
              <input
                type="checkbox"
                checked={processingConsent}
                onChange={(event) => setProcessingConsent(event.target.checked)}
              />
              <span className="check-box" aria-hidden="true">✓</span>
              <span>
                <strong>AI Voice Cloning 테스트와 외부 처리에 동의합니다.</strong>
                <small>
                  실제 모드에서는 녹음이 Fish Audio로 전송되며 생성 후 임시 Clone 삭제를 시도합니다.
                </small>
              </span>
            </label>
          </div>

          <aside className="notice-box">
            <strong>PRIVACY NOTICE</strong>
            <p>
              원본 녹음과 결과는 브라우저에서만 재생합니다. 서버는 영구 저장하지 않으며,
              삭제 결과를 화면에 표시합니다.
            </p>
          </aside>

          <div className="button-row">
            <button className="text-button" onClick={() => setView("intro")}>← 이전</button>
            <button
              className="primary-button"
              disabled={!ownVoiceConsent || !processingConsent}
              onClick={() => setView("record")}
            >
              10초 테스트 시작 <span aria-hidden="true">→</span>
            </button>
          </div>
        </section>
      )}

      {view === "record" && (
        <section className="content-panel panel-enter" aria-labelledby="record-title">
          <StepHeader
            step="02 / 04"
            title="Voice Sample Acquisition"
            description="아래 문장을 자연스러운 속도와 평소 목소리로 읽어주세요."
          />

          <div className={`recorder ${recorder.status === "recording" ? "recording" : ""}`}>
            <div className="recorder-topline">
              <span className="rec-state">
                <span className="rec-dot" />
                {recorder.status === "recording"
                  ? "RECORDING"
                  : recorder.status === "ready"
                    ? "SAMPLE READY"
                    : "MICROPHONE READY"}
              </span>
              <strong className="timer">
                {(recorder.elapsedMs / 1000).toFixed(1)}
                <small> / 10.0 SEC</small>
              </strong>
            </div>

            <blockquote>{REFERENCE_PROMPT}</blockquote>
            <LevelMeter
              level={recorder.level}
              active={recorder.status === "recording"}
            />
            <div className="timer-track">
              <span
                style={{
                  width: `${Math.min(100, (recorder.elapsedMs / RECORDING_TARGET_MS) * 100)}%`,
                }}
              />
            </div>

            {recorder.status === "idle" && (
              <button className="record-button" onClick={recorder.start}>
                <span className="record-button__dot" /> 녹음 시작
              </button>
            )}
            {recorder.status === "requesting" && (
              <p className="status-copy">마이크 권한을 확인하고 있습니다…</p>
            )}
            {recorder.status === "processing" && (
              <p className="status-copy">녹음을 16kHz WAV로 변환하고 있습니다…</p>
            )}
            {recorder.status === "recording" && (
              <p className="status-copy">10초 후 자동으로 종료됩니다.</p>
            )}
            {recorder.status === "error" && (
              <div className="inline-error" role="alert">
                <strong>녹음 실패</strong>
                <span>{recorder.error}</span>
                <button onClick={recorder.start}>다시 시도</button>
              </div>
            )}
          </div>

          {recorder.status === "ready" && recorder.audio && originalUrl && (
            <div className="recording-review">
              <AudioPlayer
                label="녹음 확인"
                description={`실제 디코딩 길이 ${(recorder.audio.durationMs / 1000).toFixed(2)}초`}
                src={originalUrl}
              />
              <div className="button-row">
                <button className="secondary-button" onClick={recorder.reset}>다시 녹음</button>
                <button className="primary-button" onClick={() => setView("phrase")}>
                  이 녹음 사용 <span aria-hidden="true">→</span>
                </button>
              </div>
            </div>
          )}
        </section>
      )}

      {view === "phrase" && recorder.audio && (
        <section className="content-panel panel-enter" aria-labelledby="phrase-title">
          <StepHeader
            step="03 / 04"
            title="생성 문장 선택"
            description="임의 문장은 입력할 수 없습니다. 아래 안전 문장 중 하나를 선택하세요."
          />

          <div className="phrase-list">
            {(Object.entries(SAFE_PHRASES) as Array<[SafePhraseId, string]>).map(
              ([id, phrase], index) => (
                <label className={phraseId === id ? "phrase-card selected" : "phrase-card"} key={id}>
                  <input
                    type="radio"
                    name="phrase"
                    value={id}
                    checked={phraseId === id}
                    onChange={() => setPhraseId(id)}
                  />
                  <span className="phrase-index">{String.fromCharCode(65 + index)}</span>
                  <span>{phrase}</span>
                  <span className="radio-indicator" />
                </label>
              ),
            )}
          </div>

          <div className="button-row">
            <button className="text-button" onClick={() => setView("record")}>← 녹음으로</button>
            <button className="danger-button" onClick={runAttack}>
              내 AI 음성으로 생성 <span aria-hidden="true">⚡</span>
            </button>
          </div>
        </section>
      )}

      {view === "processing" && (
        <section className="content-panel processing-panel panel-enter" aria-labelledby="processing-title">
          <StepHeader
            step="04 / 04"
            title="Attack in Progress"
            description="실제 서버와 Voice Provider의 현재 단계를 표시합니다."
          />

          <div className="elapsed-display">
            <small>ELAPSED TIME</small>
            <strong>{(elapsedMs / 1000).toFixed(1)}</strong>
            <span>SEC</span>
          </div>

          <ol className="progress-list">
            {STAGE_ORDER.map((stage, index) => {
              const active = stage.id === activeStage;
              const complete = index < completedStageIndex;
              return (
                <li
                  className={active ? "active" : complete ? "complete" : ""}
                  key={stage.id}
                >
                  <span className="progress-number">{complete ? "✓" : stage.number}</span>
                  <span>
                    <strong>{stage.label}</strong>
                    {active && <small>{stageMessage}</small>}
                  </span>
                  {active && <span className="spinner" aria-label="처리 중" />}
                </li>
              );
            })}
          </ol>

          <button className="text-button cancel-button" onClick={cancelRequest}>요청 취소</button>
        </section>
      )}

      {view === "result" && result && recorder.audio && originalUrl && (
        <section className="content-panel result-panel panel-enter" aria-labelledby="result-title">
          <div className="result-status">
            <span className="result-check">✓</span>
            <div>
              <small>{result.provider === "mock" ? "SIMULATION COMPLETE" : "VOICE CLONE GENERATED"}</small>
              <h2 id="result-title">
                당신은 이 문장을
                <br /> 실제로 말한 적이 없습니다.
              </h2>
            </div>
          </div>

          {result.provider === "mock" && (
            <aside className="mock-banner">
              <strong>MOCK PROVIDER</strong>
              <span>
                현재 결과는 흐름 검증용 합성 톤입니다. Fish Audio 키를 설정하면 실제 복제 음성이 생성됩니다.
              </span>
            </aside>
          )}

          {!result.cleanupCompleted && (
            <aside className="cleanup-warning" role="alert">
              <strong>Provider Clone 삭제를 확인하지 못했습니다.</strong>
              <span>Production 공개 전 영구 정리 큐를 연결해야 합니다.</span>
            </aside>
          )}

          <div className="audio-grid">
            <AudioPlayer
              label="Original Voice"
              description={`${formatDuration(result.timings.recordingMs)} captured sample`}
              src={originalUrl}
            />
            <AudioPlayer
              label="AI Generated Voice"
              description={SAFE_PHRASES[phraseId]}
              src={result.generatedUrl}
              tone="generated"
            />
          </div>

          <div className="timing-grid">
            <Timing label="음성 검증" value={result.timings.validationMs} />
            <Timing label="Voice Clone" value={result.timings.cloneMs} />
            <Timing label="새 문장 생성" value={result.timings.generationMs} />
            <Timing label="총 Attack Time" value={result.timings.totalMs} featured />
          </div>

          <div className="result-message">
            <span>10 SEC → NEW VOICE</span>
            <p>AI가 단 10초의 음성만으로 새로운 문장을 생성했습니다.</p>
          </div>

          <button className="primary-button centered" onClick={resetAll}>
            테스트 종료 및 로컬 데이터 삭제
          </button>
        </section>
      )}

      {view === "error" && (
        <section className="content-panel error-panel panel-enter" role="alert">
          <span className="error-symbol">!</span>
          <small>ATTACK INTERRUPTED</small>
          <h2>처리를 완료하지 못했습니다.</h2>
          <p>{error?.message}</p>
          {error?.requestId && error.requestId !== "local" && (
            <code>Request ID: {error.requestId}</code>
          )}
          <div className="button-row centered-row">
            <button className="secondary-button" onClick={resetAll}>처음부터</button>
            {error?.retryable && recorder.audio && (
              <button className="primary-button" onClick={() => setView("phrase")}>
                녹음 유지하고 다시 시도
              </button>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

function StepHeader({
  step,
  title,
  description,
}: {
  step: string;
  title: string;
  description: string;
}) {
  return (
    <header className="step-header">
      <span>{step}</span>
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
    </header>
  );
}

function Timing({
  label,
  value,
  featured = false,
}: {
  label: string;
  value: number;
  featured?: boolean;
}) {
  return (
    <div className={featured ? "timing featured" : "timing"}>
      <small>{label}</small>
      <strong>{(value / 1000).toFixed(1)}</strong>
      <span>SEC</span>
    </div>
  );
}

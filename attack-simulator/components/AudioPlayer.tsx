"use client";

type AudioPlayerProps = {
  label: string;
  description: string;
  src: string;
  tone?: "original" | "generated";
};

export function AudioPlayer({
  label,
  description,
  src,
  tone = "original",
}: AudioPlayerProps) {
  return (
    <section className={`audio-card audio-card--${tone}`}>
      <div className="audio-card__header">
        <span className="audio-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 10v4" />
          </svg>
        </span>
        <span>
          <small>{tone === "original" ? "SOURCE AUDIO" : "SYNTHETIC AUDIO"}</small>
          <strong>{label}</strong>
        </span>
      </div>
      <p>{description}</p>
      <audio controls preload="metadata" src={src}>
        브라우저가 오디오 재생을 지원하지 않습니다.
      </audio>
    </section>
  );
}

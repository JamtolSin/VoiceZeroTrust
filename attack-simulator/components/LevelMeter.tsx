"use client";

export function LevelMeter({ level, active }: { level: number; active: boolean }) {
  return (
    <div className="level-meter" aria-label={`입력 음량 ${Math.round(level * 100)}%`}>
      {Array.from({ length: 22 }, (_, index) => {
        const distance = Math.abs(index - 10.5) / 10.5;
        const shape = 1 - distance * 0.62;
        const movement = active
          ? Math.max(0.1, Math.min(1, level * 1.6 + ((index * 7) % 5) * 0.035))
          : 0.08;
        return (
          <span
            key={index}
            style={{ transform: `scaleY(${Math.max(0.08, shape * movement)})` }}
          />
        );
      })}
    </div>
  );
}

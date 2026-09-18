import { AttackSimulator } from "@/components/AttackSimulator";

export default function Home() {
  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="VoiceShield 홈">
          <span className="brand-mark" aria-hidden="true">
            VS
          </span>
          <span>
            <strong>VoiceShield</strong>
            <small>ATTACK LAB</small>
          </span>
        </a>
        <span className="environment-badge">
          <span className="status-dot" /> SECURITY DEMO
        </span>
      </header>

      <AttackSimulator />

      <footer className="footer">
        <p>본인 음성만 사용하세요. 목소리만으로 사람의 신원을 판단하지 마세요.</p>
        <span>VoiceZeroTrust · Educational Security Test</span>
      </footer>
    </main>
  );
}

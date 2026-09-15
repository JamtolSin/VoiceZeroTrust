import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "VoiceShield Attack Simulator",
  description:
    "본인 음성 10초로 Voice Cloning 위험을 확인하는 보안 교육용 시뮬레이터",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}

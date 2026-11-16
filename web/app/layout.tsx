import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans_Thai, IBM_Plex_Sans_Thai_Looped } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";

// Self-hosted at build time by Next, so a plant network with no internet still
// serves it: nothing is fetched from Google when a page loads.
const thai = IBM_Plex_Sans_Thai({
  subsets: ["thai", "latin"],
  weight: ["400", "600", "700"],
  variable: "--font-thai",
  display: "swap",
});

// The looped face of the same family for the rebuilt screens (ADR-133): looped
// Thai reads better at a glance (design/REQUIREMENTS.md), 400 and 600 only.
const looped = IBM_Plex_Sans_Thai_Looped({
  subsets: ["thai", "latin"],
  weight: ["400", "600"],
  variable: "--font-looped",
  display: "swap",
});

// Codes and figures in one mono weight (visual refresh, ADR-139): machine ids,
// work orders and lock numbers read as identifiers, digits line up.
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "แจ้งซ่อมล่วงหน้า",
  description: "ใบงานซ่อมบำรุงที่บอกว่าซ่อมอะไร ทำไมต้องซ่อม และซ่อมอย่างไร",
  applicationName: "แจ้งซ่อมล่วงหน้า",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Not locked: a technician reading a torque value on a phone has to be able
  // to zoom in on it.
  maximumScale: 5,
  themeColor: "#1d4ed8",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="th" className={`${thai.variable} ${looped.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}

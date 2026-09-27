import type { Metadata, Viewport } from "next";
import { IBM_Plex_Sans_Thai } from "next/font/google";
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
    <html lang="th" className={thai.variable}>
      <body>{children}</body>
    </html>
  );
}

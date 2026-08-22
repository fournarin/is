import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "ระบบแจ้งซ่อมล่วงหน้า",
  description: "ตรวจจับและคาดการณ์การซ่อมบำรุง พร้อมสั่งงานให้ช่างอัตโนมัติ",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Not locked: a technician reading a torque value on a phone has to be able
  // to zoom in on it.
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="th">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import { Heebo } from "next/font/google";
import "./globals.css";

const heebo = Heebo({ subsets: ["hebrew", "latin"], display: "swap" });

export const metadata: Metadata = {
  title: "ריצות — מרכז בקרה",
  description: "טבלת ריצות לדוגמה ב-React + TypeScript מול runs.json",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl">
      <body className={`${heebo.className} antialiased`}>{children}</body>
    </html>
  );
}

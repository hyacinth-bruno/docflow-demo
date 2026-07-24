import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DocFlow — async document pipeline demo",
  description: "Upload → extract → search, with real-time progress",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

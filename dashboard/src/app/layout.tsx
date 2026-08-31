import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SCRATCH Bot Monitor",
  description: "Real-time monitoring dashboard for SCRATCH trading bot",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

import type { Metadata } from "next";
import { Inter, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import TopNav from "@/components/nav/TopNav";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "ATLAS — Market Intelligence Engine",
  description: "Jhaveri Intelligence Platform — Market, Sector, Stock, Decision",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${sourceSerif.variable}`}
      style={
        {
          "--font-sans": "var(--font-inter), -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif",
          "--font-serif": "var(--font-source-serif), 'Source Serif Pro', Georgia, serif",
        } as React.CSSProperties
      }
    >
      <body style={{ background: "var(--bg-app)", color: "var(--text-primary)", minHeight: "100vh" }}>
        <TopNav />
        {children}
      </body>
    </html>
  );
}

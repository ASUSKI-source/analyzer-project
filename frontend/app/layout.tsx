import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { TopNav } from "@/components/layout/TopNav";
import { AIPanel } from "@/components/layout/AIPanel";
import { Background } from "@/components/layout/Background";
import { ClientProviders } from "@/providers/ClientProviders";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Stocks/Crypto AI Analyzer Pro",
  description: "Next-gen portfolio intelligence and technical analysis.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-screen flex flex-col font-sans bg-transparent`}
      >
        <ClientProviders>
          <Background />
          <TopNav />
          {/* Main layout container allows the AI Panel to overlay */}
          <div className="flex flex-1 relative overflow-hidden h-full">
            <main className="flex-1 overflow-y-auto px-6 xl:px-8 max-w-[1600px] w-full mx-auto py-8">
              {children}
            </main>
            <AIPanel />
          </div>
        </ClientProviders>
      </body>
    </html>
  );
}

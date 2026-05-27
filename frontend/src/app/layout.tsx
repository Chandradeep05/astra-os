import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Geist } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  weight: ["400", "500"],
});

const geistSans = Geist({
  subsets: ["latin"],
  variable: "--font-geist-sans",
});

export const metadata: Metadata = {
  title: "ASTRA OS | Intelligent Operating Environment",
  description:
    "An intelligent operating environment for AI orchestration, system intelligence, and autonomous workflows.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} ${geistSans.variable} font-sans bg-base text-foreground overflow-hidden antialiased`}
      >
        <div className="flex h-screen w-full overflow-hidden">
          <main className="flex-1 relative flex flex-col min-w-0 h-full overflow-hidden">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}

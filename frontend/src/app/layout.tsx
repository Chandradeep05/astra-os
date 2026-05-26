import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ASTRA OS | Your Local AI Ecosystem",
  description: "The AI Operating System that replaces your entire productivity stack locally, privately, permanently.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-background text-foreground overflow-hidden`}>
        <div className="flex h-screen w-full overflow-hidden">
          {/* Main Content Area */}
          <main className="flex-1 relative flex flex-col min-w-0 h-full overflow-hidden">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });

export const metadata: Metadata = {
  title: "OFFSCRIPT",
  description: "Every decision creates another game. Multi-agent counterfactual football intelligence on synthetic matches.",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        {/* Light is the default; the header toggle (or ?theme=dark|light) switches and is remembered. Runs before paint. */}
        <script dangerouslySetInnerHTML={{ __html: `(function(){var t="light";try{var q=new URLSearchParams(location.search).get("theme");if(q==="light"||q==="dark")localStorage.setItem("offscript.theme",q);t=q||localStorage.getItem("offscript.theme")||"light"}catch(e){}document.documentElement.dataset.theme=t==="dark"?"dark":"light"})()` }} />
      </head>
      <body className="min-h-screen font-sans antialiased">{children}</body>
    </html>
  );
}

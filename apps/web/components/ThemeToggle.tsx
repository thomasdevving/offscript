"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

/** Light/dark switch. The theme lives on <html data-theme>, set before paint by the root layout. */
export default function ThemeToggle({ lang = "en" }: { lang?: "en" | "nl" }) {
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  }, []);
  const next: Theme = theme === "light" ? "dark" : "light";
  const label = lang === "en" ? `Switch to ${next} theme` : next === "dark" ? "Donker thema" : "Licht thema";
  return (
    <button type="button" className="btn h-8 w-8 p-0" aria-label={label} title={label} data-testid="theme-toggle"
      onClick={() => {
        document.documentElement.dataset.theme = next;
        try {
          localStorage.setItem("parallel.theme", next);
        } catch {
          /* storage unavailable */
        }
        setTheme(next);
      }}>
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" aria-hidden>
        {theme === "light"
          ? <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z" />
          : <><circle cx={12} cy={12} r={4} /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>}
      </svg>
    </button>
  );
}

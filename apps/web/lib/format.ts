import type { Language } from "@parallel/contracts";

export function pct(v: number | null | undefined, lang: Language = "en", digits = 1): string {
  if (v == null || Number.isNaN(v)) return "-";
  const s = `${(v * 100).toFixed(digits)}%`;
  return lang === "nl" ? s.replace(".", ",") : s;
}

export function signedPp(v: number, lang: Language = "en"): string {
  const s = `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)} pp`;
  return lang === "nl" ? s.replace(".", ",") : s;
}

export function clock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function minuteOf(ms: number): number {
  return Math.floor(ms / 60000) + 1;
}

export function cleanLabel(label: string): string {
  return label.replace(" (actual)", "");
}

import type { Language } from "@offscript/contracts";

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

const OUTCOMES: Record<string, string> = {
  goal: "Goal", saved: "Saved", blocked: "Blocked", off_target: "Off target", turnover: "Lost the ball",
  success: "Success", decision: "Next decision", shot_blocked: "Shot blocked",
};

/** Simulator outcome codes in plain words ("off_target" -> "Off target"). */
export function outcomeLabel(code: string): string {
  return OUTCOMES[code] ?? code.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

const AUDIENCES: Record<string, string> = { casual: "Fan", analyst: "Analyst", broadcaster: "Broadcast" };

/** A verification or validation message in plain words, e.g. "casual/en: Unsupported percentage 19.3% (...)"
 *  -> "Fan text: a percentage (19.3%) that the simulation never produced". */
export function plainCheckIssue(raw: string): string {
  let where = "";
  let msg = raw;
  const m = raw.match(/^(casual|analyst|broadcaster)\/(\w+):\s*(.*)$/s);
  if (m) {
    where = `${AUDIENCES[m[1]]} text${m[2] !== "en" ? ` (${m[2].toUpperCase()})` : ""}: `;
    msg = m[3];
  }
  const rules: [RegExp, (g: RegExpMatchArray) => string][] = [
    [/^Unknown evidence references/, () => "cited a source field that does not exist"],
    [/^Unsupported percentage ([\d.,-]+)%/, (g) => `a percentage (${g[1]}%) that the simulation never produced`],
    [/^Unsupported number ([\d.,-]+)/, (g) => `a number (${g[1]}) that is not in the evidence`],
    [/^Overclaiming language: '(.*)'/, (g) => `too certain wording ("${g[1]}")`],
    [/^Mentions (.*), who is not part of this decision/, (g) => `mentions ${g[1]}, who is not part of this moment`],
    [/^Missing model qualifier/, () => "did not say it is a model estimate"],
    [/^Broadcast caption longer/, () => "caption too long for broadcast"],
    [/^[A-Z_]+: (.*)$/s, (g) => g[1]],
  ];
  for (const [re, fn] of rules) {
    const g = msg.match(re);
    if (g) return where + fn(g);
  }
  return where + msg;
}

import type { Language } from "@offscript/contracts";

export function pct(v: number | null | undefined, lang: Language = "en", digits = 1): string {
  if (v == null || Number.isNaN(v)) return "-";
  const s = `${(v * 100).toFixed(digits)}%`;
  return lang !== "en" ? s.replace(".", ",") : s;
}

export function signedPp(v: number, lang: Language = "en"): string {
  const s = `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)} pp`;
  return lang !== "en" ? s.replace(".", ",") : s;
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

// Option labels come from the simulator in English; they follow the viewer's language (set by the store).
let labelLang: Language = "en";
export function setLabelLanguage(lang: Language): void {
  labelLang = lang;
}

const DRIBBLES: Record<string, Partial<Record<Language, string>>> = {
  "Dribble towards goal": { nl: "Dribbel richting doel", es: "Regate hacia la portería", fr: "Dribble vers le but", de: "Dribbling Richtung Tor" },
  "Dribble diagonally right": { nl: "Dribbel schuin naar rechts", es: "Regate en diagonal a la derecha", fr: "Dribble en diagonale à droite", de: "Dribbling diagonal nach rechts" },
  "Dribble diagonally left": { nl: "Dribbel schuin naar links", es: "Regate en diagonal a la izquierda", fr: "Dribble en diagonale à gauche", de: "Dribbling diagonal nach links" },
  "Dribble wide right": { nl: "Dribbel naar rechts buiten", es: "Regate por la banda derecha", fr: "Dribble côté droit", de: "Dribbling über rechts" },
  "Dribble wide left": { nl: "Dribbel naar links buiten", es: "Regate por la banda izquierda", fr: "Dribble côté gauche", de: "Dribbling über links" },
};

/** "Pass to Mbeki-Larsen (actual)" -> "Pase a Mbeki-Larsen" in the viewer's language. */
export function cleanLabel(label: string, lang: Language = labelLang): string {
  const base = label.replace(" (actual)", "");
  if (lang === "en") return base;
  if (base === "Shoot") return { nl: "Schieten", es: "Tiro", fr: "Tir", de: "Schuss" }[lang];
  const pass = /^(Through ball|Pass) to (.+)$/.exec(base);
  if (pass) {
    const [through, who] = [pass[1] === "Through ball", pass[2]];
    return {
      nl: through ? `Steekpass naar ${who}` : `Pass naar ${who}`,
      es: through ? `Pase al hueco a ${who}` : `Pase a ${who}`,
      fr: through ? `Passe en profondeur à ${who}` : `Passe à ${who}`,
      de: through ? `Steilpass zu ${who}` : `Pass zu ${who}`,
    }[lang];
  }
  return DRIBBLES[base]?.[lang] ?? base;
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
    [/^Uses an internal identifier \((.*)\)/, (g) => `used an internal code (${g[1]}) instead of plain words`],
    [/^Uses the internal player id (\S+) instead of the name (.*)$/, (g) => `used a player code (${g[1]}) instead of the name ${g[2]}`],
    [/^[A-Z_]+: (.*)$/s, (g) => g[1]],
  ];
  for (const [re, fn] of rules) {
    const g = msg.match(re);
    if (g) return where + fn(g);
  }
  return where + msg;
}

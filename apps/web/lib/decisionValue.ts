import type { DecisionValueAggregate, DecisionValueReport, Language, ViewerMode } from "@offscript/contracts";

/** Probability -> percentage points with one decimal ("1.8"), Dutch decimal comma. */
export function pp(v: number, lang: Language = "en"): string {
  const s = (Math.abs(v) < 0.0005 ? 0 : v * 100).toFixed(1);
  return lang === "nl" ? s.replace(".", ",") : s;
}

/** "Left on the table" is the negated DVA: a positive amount and its interval, in pp. */
export function leftOnTable(a: DecisionValueAggregate, lang: Language = "en"): { value: string; low: string; high: string } | null {
  if (!a.enough_decisions || a.dva_sum == null || a.dva_sum_ci95_low == null || a.dva_sum_ci95_high == null) return null;
  return { value: pp(-a.dva_sum, lang), low: pp(-a.dva_sum_ci95_high, lang), high: pp(-a.dva_sum_ci95_low, lang) };
}

/** Player whose choices left the most modelled goal chance on the table (only players with enough decisions). */
export function headlinePlayer(r: DecisionValueReport): DecisionValueAggregate | null {
  const ok = r.players.filter((p) => p.enough_decisions && p.dva_sum != null);
  if (!ok.length) return null;
  return ok.reduce((a, b) => ((b.dva_sum ?? 0) < (a.dva_sum ?? 0) ? b : a));
}

/**
 * One sentence for the current viewer mode, built only from numbers in the report.
 * Example (broadcaster): "Castellane's choices left 1.8 pp of modelled goal chance on the table this match (95% interval 0.4-3.2 pp, 4 decisions)."
 */
export function oneLiner(r: DecisionValueReport, mode: ViewerMode, lang: Language = "en",
  shortNames: Record<string, string> = {}): string {
  const en = lang === "en";
  const p = headlinePlayer(r);
  if (!p) {
    return en
      ? `Not enough analysed decisions per player yet (minimum ${r.min_decisions}; ${r.decisions_analysed} of ${r.decisions_detected} decisions analysed).`
      : `Nog niet genoeg geanalyseerde beslissingen per speler (minimaal ${r.min_decisions}; ${r.decisions_analysed} van ${r.decisions_detected} beslissingen geanalyseerd).`;
  }
  const lt = leftOnTable(p, lang)!;
  const n = p.n_decisions;
  if ((p.dva_sum ?? 0) === 0) {
    return en
      ? `Under the model, ${p.name} picked the best available option at all ${n} analysed decisions (95% interval for modelled goal chance left: ${lt.low}-${lt.high} pp).`
      : `Volgens het model koos ${p.name} bij alle ${n} geanalyseerde beslissingen de beste optie (95%-interval voor gemiste gemodelleerde doelkans: ${lt.low}-${lt.high} pp).`;
  }
  if (mode === "analyst") {
    const mean = pp(p.dva_mean ?? 0, lang);
    return en
      ? `${p.name}: DVA ${pp(p.dva_sum ?? 0, lang)} pp over ${n} decisions (95% interval ${pp(p.dva_sum_ci95_low ?? 0, lang)} to ${pp(p.dva_sum_ci95_high ?? 0, lang)} pp; mean ${mean} pp per decision; ${p.clear_misses} with a clearly better alternative).`
      : `${p.name}: DVA ${pp(p.dva_sum ?? 0, lang)} pp over ${n} beslissingen (95%-interval ${pp(p.dva_sum_ci95_low ?? 0, lang)} tot ${pp(p.dva_sum_ci95_high ?? 0, lang)} pp; gemiddeld ${mean} pp per beslissing; ${p.clear_misses} met een duidelijk betere optie).`;
  }
  if (mode === "casual") {
    return en
      ? `Under our simulation model, ${p.name} could have added about ${lt.value} percentage points of goal chance across ${n} decisions by always taking the model's best option (95% interval ${lt.low}-${lt.high}).`
      : `Volgens ons simulatiemodel had ${p.name} over ${n} beslissingen ongeveer ${lt.value} procentpunt doelkans kunnen toevoegen door steeds de beste optie van het model te kiezen (95%-interval ${lt.low}-${lt.high}).`;
  }
  const who = shortNames[p.key] ?? p.name;
  return en
    ? `${who}'s choices left ${lt.value} pp of modelled goal chance on the table this match (95% interval ${lt.low}-${lt.high} pp, ${n} decisions).`
    : `De keuzes van ${who} lieten deze wedstrijd ${lt.value} pp gemodelleerde doelkans liggen (95%-interval ${lt.low}-${lt.high} pp, ${n} beslissingen).`;
}

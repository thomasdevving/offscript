import type { CounterfactualAnalysis, Language, MatchEvent, Overlay, ViewerMode } from "@offscript/contracts";

/**
 * Picks the overlay to show at simulation time `t` for a viewer.
 *
 * Rules (mirrors the machine-readable overlay contract):
 * - an overlay is eligible during [sim_time_ms, sim_time_ms + duration_ms);
 * - it expires early when an event listed in `expires.on_event_types` happens after it started
 *   (e.g. a goal clears an older decision card), or after `max_age_ms`;
 * - among eligible overlays the highest priority wins; ties go to the most recent.
 */
export function activeOverlay(
  overlays: Overlay[],
  t: number,
  mode: ViewerMode,
  lang: Language,
  events: Pick<MatchEvent, "event_type" | "sim_time_ms">[],
): Overlay | null {
  let best: Overlay | null = null;
  for (const o of overlays) {
    if (o.viewer_mode !== mode || o.language !== lang) continue;
    const start = o.sim_time_ms;
    let end = start + o.duration_ms;
    if (o.expires?.max_age_ms != null) end = Math.min(end, start + o.expires.max_age_ms);
    if (t < start || t >= end) continue;
    const killers = o.expires?.on_event_types ?? [];
    const killed = events.some(
      (e) => killers.includes(e.event_type) && e.sim_time_ms > start && e.sim_time_ms <= t && !(o.type === "goal" && e.event_type === "GOAL"),
    );
    if (killed) continue;
    if (!best || o.priority > best.priority || (o.priority === best.priority && o.sim_time_ms > best.sim_time_ms)) best = o;
  }
  return best;
}

/**
 * Overlays are produced in English and Dutch. For Spanish, French and German the English overlay keeps
 * its timing, priority and expiry rules, and its text is replaced by that analysis' verified broadcast
 * narrative in the viewer's language when it is available.
 */
export function localizeOverlays(overlays: Overlay[], analyses: CounterfactualAnalysis[], lang: Language): Overlay[] {
  if (lang === "en" || lang === "nl") return overlays;
  const byId = new Map(analyses.map((a) => [a.analysis_id, a]));
  return overlays.filter((o) => o.language === "en").map((o) => {
    const n = byId.get(o.analysis_id ?? "")?.narratives.find((x) => x.audience === "broadcaster" && x.language === lang);
    return n ? { ...o, language: lang, headline: n.headline, caption: n.caption ?? o.caption, narrative: n.body }
      : { ...o, language: lang };
  });
}

"use client";

import type { FaultInjection } from "@offscript/contracts";
import { t, tr } from "@/lib/i18n";
import { actions, useApp } from "@/lib/store";

const FAULTS: { id: FaultInjection; en: string; nl: string; es: string; fr: string; de: string }[] = [
  { id: "invalid_candidate", en: "Impossible pass", nl: "Onmogelijke pass", es: "Pase imposible", fr: "Passe impossible",
    de: "Unmöglicher Pass" },
  { id: "contradictory_claim", en: "False number in the story", nl: "Vals getal in het verhaal",
    es: "Dato falso en la historia", fr: "Chiffre faux dans le récit", de: "Falsche Zahl im Text" },
  { id: "model_unavailable", en: "AI model outage", nl: "AI-model valt uit", es: "Caída del modelo de IA",
    fr: "Panne du modèle d'IA", de: "KI-Modell fällt aus" },
  { id: "simulation_timeout", en: "Simulation cut short", nl: "Simulatie afgekapt", es: "Simulación interrumpida",
    fr: "Simulation interrompue", de: "Simulation abgebrochen" },
];

export default function RecoveryPanel() {
  const s = useApp();
  const L = t(s.lang);
  return (
    <section className="border-t border-white/5 px-1 pt-3" aria-label={L.recovery} data-testid="recovery-panel">
      <h2 className="eyebrow">{L.recovery}</h2>
      <p className="mt-1 text-[11px] text-slate-500">{L.recoveryHint}</p>
      <div className="mt-2 grid grid-cols-2 gap-1.5">
        {FAULTS.map((f) => (
          <button key={f.id} type="button" onClick={() => void actions.runRecovery(f.id)} data-testid={`fault-${f.id}`}
            className={`rounded-lg px-2 py-1.5 text-xs font-semibold transition ${s.recoveryFault === f.id ? "bg-red-500/20 text-red-100 ring-1 ring-red-400/60" : "bg-white/[0.04] text-slate-200 hover:bg-white/[0.08]"}`}>
            {tr(s.lang, f)}
          </button>
        ))}
      </div>
    </section>
  );
}

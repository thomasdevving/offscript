"use client";

import type { FaultInjection } from "@parallel/contracts";
import { t } from "@/lib/i18n";
import { actions, useApp } from "@/lib/store";

const FAULTS: { id: FaultInjection; en: string; nl: string }[] = [
  { id: "invalid_candidate", en: "Invalid alternative", nl: "Ongeldig alternatief" },
  { id: "contradictory_claim", en: "Contradictory claim", nl: "Tegenstrijdige claim" },
  { id: "model_unavailable", en: "Model outage", nl: "Model-storing" },
  { id: "simulation_timeout", en: "Simulation timeout", nl: "Simulatie-timeout" },
];

export default function RecoveryPanel() {
  const s = useApp();
  const L = t(s.lang);
  return (
    <section className="rounded-xl border border-line bg-panel p-3" aria-label={L.recovery} data-testid="recovery-panel">
      <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">{L.recovery}</h2>
      <p className="mt-1 text-[11px] text-slate-500">{L.recoveryHint}</p>
      <div className="mt-2 grid grid-cols-2 gap-1.5">
        {FAULTS.map((f) => (
          <button key={f.id} type="button" onClick={() => void actions.runRecovery(f.id)} data-testid={`fault-${f.id}`}
            className={`rounded-md border px-2 py-1.5 text-xs font-semibold ${s.recoveryFault === f.id ? "border-red-400 bg-red-500/15 text-red-100" : "border-line bg-slate-900 text-slate-200 hover:bg-slate-800"}`}>
            {s.lang === "en" ? f.en : f.nl}
          </button>
        ))}
      </div>
    </section>
  );
}

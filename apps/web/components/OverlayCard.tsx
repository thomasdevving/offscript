"use client";

import type { Overlay } from "@parallel/contracts";

/** Renders one machine-readable overlay instruction on top of the pitch. */
export default function OverlayCard({ overlay }: { overlay: Overlay }) {
  const pos = String(overlay.render_hint?.position ?? "pitch_card");
  if (overlay.type === "goal") {
    return (
      <div className="pointer-events-none absolute inset-x-0 top-1/3 z-20 flex justify-center" role="status" aria-live="polite">
        <div className="animate-pop rounded-xl bg-emerald-500/95 px-8 py-3 text-center shadow-2xl">
          <div className="text-3xl font-black tracking-widest text-emerald-950">{overlay.headline}</div>
          <div className="text-sm font-semibold text-emerald-950">{overlay.narrative}</div>
        </div>
      </div>
    );
  }
  if (pos === "lower_third" || overlay.viewer_mode === "broadcaster") {
    return (
      <div className="pointer-events-none absolute inset-x-4 bottom-4 z-20" role="status" aria-live="polite" data-testid="overlay">
        <div className="animate-slide flex items-stretch overflow-hidden rounded-lg shadow-2xl">
          <div className="flex items-center bg-blue-600 px-3 text-xs font-black uppercase tracking-widest text-white">PARALLEL</div>
          <div className="flex-1 bg-slate-950/95 px-4 py-2">
            <div className="text-sm font-extrabold uppercase tracking-wide text-white">{overlay.headline}</div>
            <div className="text-sm text-blue-100">{overlay.caption ?? overlay.narrative}</div>
          </div>
          <div className="flex items-center gap-3 bg-slate-900/95 px-3">
            {overlay.data_fields.slice(0, 2).map((f) => (
              <div key={f.key} className="text-center">
                <div className="font-mono text-lg font-bold text-white">{f.display}</div>
                <div className="max-w-28 truncate text-[10px] uppercase text-slate-400">{f.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="pointer-events-none absolute bottom-4 right-4 z-20 max-w-sm" role="status" aria-live="polite" data-testid="overlay">
      <div className="animate-slide rounded-xl border border-blue-400/40 bg-slate-950/90 p-3 shadow-2xl backdrop-blur">
        <div className="text-xs font-bold uppercase tracking-widest text-blue-300">{overlay.headline}</div>
        <p className="mt-1 text-sm leading-snug text-slate-100">{overlay.narrative}</p>
        <div className="mt-2 flex gap-3">
          {overlay.data_fields.map((f) => (
            <div key={f.key}>
              <div className="font-mono text-base font-bold text-white">{f.display}</div>
              <div className="text-[10px] uppercase text-slate-400">{f.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

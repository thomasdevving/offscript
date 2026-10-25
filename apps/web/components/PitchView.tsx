"use client";

import dynamic from "next/dynamic";
import { actions, useApp } from "@/lib/store";
import Pitch, { type PitchProps } from "./Pitch";

// three.js only loads once someone switches to 3D.
const Pitch3D = dynamic(() => import("./Pitch3D"), {
  ssr: false,
  loading: () => <div className="flex aspect-[111/74] w-full animate-pulse items-center justify-center bg-white/[0.02] text-sm text-slate-500">Loading 3D…</div>,
});

/** The pitch in the viewer's chosen dimension: same props, same timeline, either renderer. */
export default function PitchView(p: PitchProps) {
  const dim = useApp((s) => s.pitchDim);
  return dim === "3d" ? <Pitch3D {...p} /> : <Pitch {...p} />;
}

export function DimToggle() {
  const dim = useApp((s) => s.pitchDim);
  const lang = useApp((s) => s.lang);
  return (
    <div role="radiogroup" aria-label={lang !== "nl" ? "Pitch view" : "Veldweergave"} data-testid="dim-toggle"
      className="flex bg-slate-950/80 p-0.5 ring-1 ring-white/10 backdrop-blur">
      {(["2d", "3d"] as const).map((v) => (
        <button key={v} type="button" role="radio" aria-checked={dim === v} onClick={() => actions.setPitchDim(v)}
          className="tab px-2.5 py-1 text-[11px]" data-testid={`dim-${v}`}
          title={v === "2d" ? (lang !== "nl" ? "Tactical board" : "Tactisch bord") : (lang !== "nl" ? "3D replay" : "3D-herhaling")}>
          {v.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

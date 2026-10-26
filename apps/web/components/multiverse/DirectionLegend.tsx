import type { ReactNode } from "react";
import { directionStyle, type Motion } from "@/lib/pitchDirections";

function DirectionKey({ motion, defence, observed, children }: { motion: Motion; defence?: boolean; observed?: boolean; children: ReactNode }) {
  const { dash } = directionStyle(defence ? "defense" : observed ? "actual" : "selected", motion);
  return <span className={defence ? "mv-defence-key" : observed ? "mv-observed-key" : undefined}>
    <svg viewBox="0 0 46 12" aria-hidden="true">
      <path d="M1 6h35" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeDasharray={dash?.map((v) => v * 3).join(" ")} />
      {[16, 29].map((x) => <path key={x} d={`M${x - 2.4} 3.6 ${x} 6 ${x - 2.4} 8.4`} fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />)}
      <path d="m36 2 8 4-8 4z" fill="currentColor" />
    </svg>{children}
  </span>;
}

export default function DirectionLegend() {
  return (
    <div className="mv-direction-legend" aria-label="Action direction legend">
      <DirectionKey motion="pass">Pass</DirectionKey>
      <DirectionKey motion="dribble">Dribble</DirectionKey>
      <DirectionKey motion="shoot">Shot</DirectionKey>
      <DirectionKey motion="run" defence>Defence</DirectionKey>
      <DirectionKey motion="shoot" observed>Observed (ACT)</DirectionKey>
      <span>Numbers match the options</span>
    </div>
  );
}

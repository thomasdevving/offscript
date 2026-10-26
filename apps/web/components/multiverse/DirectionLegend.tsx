export default function DirectionLegend() {
  return (
    <div className="mv-direction-legend" aria-label="Action direction legend">
      <span><svg viewBox="0 0 36 12" aria-hidden="true"><path d="M1 6h26" stroke="currentColor" strokeWidth="2" strokeDasharray="6 3" /><path d="m26 2 8 4-8 4z" fill="currentColor" /></svg>Pass</span>
      <span><svg viewBox="0 0 36 12" aria-hidden="true"><path d="M1 6h26" stroke="currentColor" strokeWidth="2" strokeDasharray="1 3" strokeLinecap="round" /><path d="m26 2 8 4-8 4z" fill="currentColor" /></svg>Dribble</span>
      <span><svg viewBox="0 0 36 12" aria-hidden="true"><path d="M1 6h26" stroke="currentColor" strokeWidth="2" /><path d="m26 2 8 4-8 4z" fill="currentColor" /></svg>Shot</span>
      <span className="mv-defence-key"><svg viewBox="0 0 36 12" aria-hidden="true"><path d="M1 6h26" stroke="currentColor" strokeWidth="2" strokeDasharray="2 3" /><path d="m26 2 8 4-8 4z" fill="currentColor" /></svg>Defence</span>
      <span>Numbers match the options · ACT = observed</span>
    </div>
  );
}

/**
 * PARALLEL mark: two offset pitch panels (the observed game and its parallel) sharing one set of pitch
 * markings, separated by a transparent gap. Vector recreation of the brand logo (also public/icon.svg).
 */
export const MARK_LEFT = "M30 27 Q27 25.5 27 29 L27 78 Q27 81.5 30 80 L50 69 Q53 67.5 53 64 L53 42 Q53 38.5 50 37 Z";
export const MARK_RIGHT = "M45 18 Q40 16 40.5 21 Q41 26 47 29.5 Q56 34 56.5 40 L56.5 66.5 L71 58.5 Q75 56.5 75 52 L75 37 Q75 31.5 70 29.5 Z";

/** One continuous set of pitch markings across both panels. */
function Markings() {
  return (
    <g fill="none" stroke="#eef6ea" strokeWidth={0.65} strokeLinejoin="round" opacity={0.92}>
      <path d="M37.4 53 L67.5 43.4" />
      <ellipse cx="54.3" cy="48" rx="10.6" ry="5" transform="rotate(-12 54.3 48)" />
      <path d="M26 47.2 L32.2 45.5 L32.6 59 L26 62" />
      <path d="M32.2 45.5 Q41 50 38.6 56 Q36.4 62 26 68.4" />
      <path d="M66.5 36.6 L76 32.8 M66.5 36.6 L76 44.6" />
      <path d="M67.6 38.2 Q64.6 43 69 45 Q72.2 46.3 76 46" />
    </g>
  );
}

export default function BrandMark({ size = 28, id = "pm" }: { size?: number; id?: string }) {
  return (
    <svg width={size} height={size} viewBox="22 14 58 70" aria-hidden>
      <defs>
        <linearGradient id={`${id}-l`} x1="0.1" y1="1" x2="0.9" y2="0">
          <stop offset="0" stopColor="#0e3424" />
          <stop offset="0.55" stopColor="#1f4f36" />
          <stop offset="1" stopColor="#6b9a72" />
        </linearGradient>
        <linearGradient id={`${id}-r`} x1="0.1" y1="0.9" x2="0.9" y2="0.05">
          <stop offset="0" stopColor="#4f8a57" />
          <stop offset="0.6" stopColor="#7aab78" />
          <stop offset="1" stopColor="#cfe2b4" />
        </linearGradient>
        <mask id={`${id}-gap`}>
          <rect x="0" y="0" width="100" height="100" fill="white" />
          <path d={MARK_RIGHT} fill="black" stroke="black" strokeWidth={3.2} strokeLinejoin="round" />
        </mask>
        <clipPath id={`${id}-cl`}><path d={MARK_LEFT} /></clipPath>
        <clipPath id={`${id}-cr`}><path d={MARK_RIGHT} /></clipPath>
      </defs>
      <path d={MARK_LEFT} fill={`url(#${id}-l)`} mask={`url(#${id}-gap)`} />
      <path d={MARK_RIGHT} fill={`url(#${id}-r)`} />
      <g clipPath={`url(#${id}-cl)`}>
        <g mask={`url(#${id}-gap)`}><Markings /></g>
      </g>
      <g clipPath={`url(#${id}-cr)`}><Markings /></g>
    </svg>
  );
}

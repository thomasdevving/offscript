export default function ActionDirectionIcon({ angle }: { angle: number }) {
  return <span className="mv-option-direction" aria-hidden="true">
    <svg viewBox="0 0 28 28"><g transform={`rotate(${angle} 14 14)`}>
      <path d="M5 14h16m-6-6 6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </g></svg>
  </span>;
}

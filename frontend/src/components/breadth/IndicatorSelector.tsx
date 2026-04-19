interface IndicatorSelectorProps {
  indicator: string;
  onIndicatorChange: (i: string) => void;
}

const INDICATORS = [
  { value: "ema21", label: "21-EMA" },
  { value: "dma50", label: "50-DMA" },
  { value: "dma200", label: "200-DMA" },
];

export default function IndicatorSelector({
  indicator,
  onIndicatorChange,
}: IndicatorSelectorProps) {
  return (
    <div className="flex gap-2" role="group" aria-label="Indicator selector">
      {INDICATORS.map((ind) => {
        const isActive = indicator === ind.value;
        return (
          <button
            key={ind.value}
            onClick={() => onIndicatorChange(ind.value)}
            className={[
              "px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors",
              isActive
                ? "border-accent-700 text-accent-700 bg-accent-50"
                : "border-gray-300 text-gray-600 bg-white hover:border-gray-400",
            ].join(" ")}
            style={isActive ? { color: "var(--accent-700)", borderColor: "var(--accent-700)" } : undefined}
            aria-pressed={isActive}
          >
            {ind.label}
          </button>
        );
      })}
    </div>
  );
}

interface UniverseSelectorProps {
  universe: string;
  onUniverseChange: (u: string) => void;
}

const UNIVERSES = [
  { value: "nifty50", label: "Nifty 50" },
  { value: "nifty200", label: "Nifty 200" },
  { value: "nifty500", label: "Nifty 500" },
];

export default function UniverseSelector({
  universe,
  onUniverseChange,
}: UniverseSelectorProps) {
  return (
    <div className="flex gap-2" role="group" aria-label="Universe selector">
      {UNIVERSES.map((u) => {
        const isActive = universe === u.value;
        return (
          <button
            key={u.value}
            onClick={() => onUniverseChange(u.value)}
            className={[
              "px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors",
              isActive
                ? "border-accent-700 text-accent-700 bg-accent-50"
                : "border-gray-300 text-gray-600 bg-white hover:border-gray-400",
            ].join(" ")}
            style={isActive ? { color: "var(--accent-700)", borderColor: "var(--accent-700)" } : undefined}
            aria-pressed={isActive}
          >
            {u.label}
          </button>
        );
      })}
    </div>
  );
}

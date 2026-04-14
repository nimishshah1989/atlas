"use client";

export function MetricCard({
  label,
  value,
  sub,
  colorClass,
}: {
  label: string;
  value: string;
  sub?: string;
  colorClass?: string;
}) {
  return (
    <div className="border rounded-lg p-3 bg-white">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-lg font-semibold ${colorClass ?? "text-gray-900"}`}>
        {value}
      </div>
      {sub && <div className="text-xs text-gray-400 mt-0.5">{sub}</div>}
    </div>
  );
}

export function PillarSection({
  title,
  items,
  explanation,
}: {
  title: string;
  items: { label: string; value: string; colorClass?: string }[];
  explanation: string;
}) {
  return (
    <div className="border rounded-lg p-4">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
        {title}
      </h4>
      <div className="grid grid-cols-2 gap-3 mb-3">
        {items.map((item) => (
          <div key={item.label}>
            <div className="text-xs text-gray-400">{item.label}</div>
            <div
              className={`text-sm font-medium mt-0.5 ${item.colorClass ?? "text-gray-900"}`}
            >
              {item.value}
            </div>
          </div>
        ))}
      </div>
      {explanation && (
        <p className="text-xs text-gray-500 border-t pt-2">{explanation}</p>
      )}
    </div>
  );
}

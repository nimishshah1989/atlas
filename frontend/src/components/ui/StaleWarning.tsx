interface StaleWarningProps {
  dataAsOf?: string | null;
}

export default function StaleWarning({ dataAsOf }: StaleWarningProps) {
  return (
    <div
      className="staleness-banner flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded text-amber-800 text-sm mb-2"
      data-staleness-banner="true"
      role="alert"
    >
      <span aria-hidden="true">&#9888;</span>
      <span>
        Data may be stale. Last updated:{" "}
        {dataAsOf ? (
          <time dateTime={dataAsOf}>{dataAsOf}</time>
        ) : (
          "unknown"
        )}
      </span>
    </div>
  );
}

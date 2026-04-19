interface EmptyStateProps {
  title?: string;
  body?: string;
}

export default function EmptyState({
  title = "No data available",
  body = "This data source has no records for the selected period.",
}: EmptyStateProps) {
  return (
    <div
      className="empty-state flex flex-col items-center justify-center py-10 text-center"
      role="status"
      aria-live="polite"
    >
      <div className="text-4xl text-gray-400 mb-3" aria-hidden="true">
        &#8709;
      </div>
      <p className="font-semibold text-gray-700">{title}</p>
      <p className="text-sm text-gray-500 mt-1">{body}</p>
    </div>
  );
}

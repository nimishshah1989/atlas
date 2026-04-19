interface ErrorBannerProps {
  code?: string;
  message?: string;
}

export default function ErrorBanner({
  code = "UNKNOWN_ERROR",
  message = "An unexpected error occurred.",
}: ErrorBannerProps) {
  return (
    <div
      className="error-card p-4 border border-red-200 bg-red-50 rounded"
      role="alert"
    >
      <div className="flex items-center gap-2 mb-1">
        <span aria-hidden="true">&#9888;</span>
        <span className="font-mono text-sm font-semibold text-red-700">{code}</span>
      </div>
      <p className="text-sm text-red-600">{message}</p>
    </div>
  );
}

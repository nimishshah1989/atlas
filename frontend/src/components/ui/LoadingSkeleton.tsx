export default function LoadingSkeleton() {
  return (
    <div className="skeleton-block animate-pulse" aria-hidden="true">
      <div className="h-4 bg-gray-200 rounded mb-3 w-full" />
      <div className="h-4 bg-gray-200 rounded mb-3 w-3/4" />
      <div className="h-4 bg-gray-200 rounded w-1/2" />
    </div>
  );
}

import { ReactNode } from "react";
import LoadingSkeleton from "./LoadingSkeleton";
import EmptyState from "./EmptyState";
import StaleWarning from "./StaleWarning";
import ErrorBanner from "./ErrorBanner";

type DataState = "loading" | "ready" | "stale" | "empty" | "error";

interface DataBlockProps {
  state: DataState;
  children?: ReactNode;
  dataClass?: string;
  dataAsOf?: string | null;
  errorCode?: string;
  errorMessage?: string;
  emptyTitle?: string;
  emptyBody?: string;
}

export default function DataBlock({
  state,
  children,
  dataClass,
  dataAsOf,
  errorCode,
  errorMessage,
  emptyTitle,
  emptyBody,
}: DataBlockProps) {
  return (
    <div
      data-state={state}
      data-data-class={dataClass ?? undefined}
      data-as-of={dataAsOf ?? undefined}
    >
      {state === "loading" && <LoadingSkeleton />}
      {state === "error" && (
        <ErrorBanner code={errorCode} message={errorMessage} />
      )}
      {state === "empty" && (
        <EmptyState title={emptyTitle} body={emptyBody} />
      )}
      {state === "stale" && (
        <>
          <StaleWarning dataAsOf={dataAsOf} />
          {children}
        </>
      )}
      {state === "ready" && children}
    </div>
  );
}

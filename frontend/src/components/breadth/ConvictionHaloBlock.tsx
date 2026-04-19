import EmptyState from "@/components/ui/EmptyState";

interface ConvictionHaloBlockProps {
  universe: string;
}

export default function ConvictionHaloBlock({ universe: _universe }: ConvictionHaloBlockProps) {
  return (
    <div data-v2-derived="true" data-block="conviction-halo">
      <EmptyState
        title="Coming soon"
        body="Conviction series will be available in a future release."
      />
    </div>
  );
}

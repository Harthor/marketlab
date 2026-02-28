// MarketLab Dashboard v2 — Skeleton loader (spec §9.5)

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = '' }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse rounded-md bg-[#182235] ${className}`}
      style={{
        backgroundImage:
          'linear-gradient(90deg, #182235 0%, #22324D 50%, #182235 100%)',
        backgroundSize: '200% 100%',
        animation: 'shimmer 1.5s ease-in-out infinite',
      }}
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="rounded-card border border-ml-border bg-ml-bg-card p-5 space-y-3">
      <div className="flex items-center gap-2">
        <Skeleton className="w-5 h-5 rounded-full" />
        <Skeleton className="h-4 w-32" />
        <div className="flex-1" />
        <Skeleton className="h-4 w-16 rounded-chip" />
      </div>
      <Skeleton className="h-3 w-48" />
      <div className="space-y-1.5 pt-1">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-4/5" />
      </div>
      <Skeleton className="h-2 w-full mt-2" />
      <Skeleton className="h-3 w-36" />
    </div>
  );
}

export function SkeletonChart() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-4 w-40" />
      <Skeleton className="h-48 w-full rounded-lg" />
    </div>
  );
}

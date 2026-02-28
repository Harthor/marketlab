// MarketLab Dashboard v2 — DashboardShell (vertical layout like Degen Scanner)

import type { ReactNode } from 'react';

interface DashboardShellProps {
  header: ReactNode;
  chips: ReactNode;
  table: ReactNode;
  detail: ReactNode;
  forecast?: ReactNode;
}

export default function DashboardShell({ header, chips, table, detail, forecast }: DashboardShellProps) {
  return (
    <div className="dashboard-page">
      {header}
      {chips}
      {table}
      {detail}
      {forecast && <div className="mt-6">{forecast}</div>}
    </div>
  );
}

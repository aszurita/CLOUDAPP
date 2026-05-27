import { AlertCircle, Loader2 } from "lucide-react";

import type { WidgetData, WidgetDef } from "../types";

type Props = {
  widget: WidgetDef;
  data: WidgetData | null;
  loading: boolean;
};

export function KpiCard({ widget, data, loading }: Props) {
  const value = extractKpiValue(data);

  return (
    <div className="df-widget-card df-kpi-card">
      {loading ? (
        <div className="df-widget-loading">
          <Loader2 size={20} className="df-spin" />
        </div>
      ) : data?.error ? (
        <div className="df-widget-error">
          <AlertCircle size={14} />
          <span>{data.error}</span>
        </div>
      ) : (
        <>
          <span className="df-kpi-value">{value}</span>
          <span className="df-kpi-label">{widget.title}</span>
        </>
      )}
    </div>
  );
}

function extractKpiValue(data: WidgetData | null): string {
  if (!data || data.rows.length === 0) return "—";
  const raw = data.rows[0][0];
  if (raw === null || raw === undefined) return "—";
  const num = Number(raw);
  if (!isNaN(num)) {
    return num >= 1_000_000
      ? `${(num / 1_000_000).toFixed(1)}M`
      : num >= 1_000
      ? `${(num / 1_000).toFixed(1)}K`
      : num % 1 === 0
      ? num.toLocaleString("es-EC")
      : num.toFixed(2);
  }
  return String(raw);
}

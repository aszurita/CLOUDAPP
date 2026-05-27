import type { DashboardSchema, WidgetData } from "../types";
import { BarChartWidget } from "./BarChartWidget";
import { DataTableWidget } from "./DataTableWidget";
import { KpiCard } from "./KpiCard";
import { LineChartWidget } from "./LineChartWidget";
import { PieChartWidget } from "./PieChartWidget";

type Props = {
  schema: DashboardSchema;
  results: WidgetData[];
  loading: boolean;
};

export function DashboardRenderer({ schema, results, loading }: Props) {
  const dataByWidget: Record<string, WidgetData> = {};
  for (const r of results) dataByWidget[r.widget_id] = r;

  return (
    <div className="df-renderer">
      <div className="df-renderer-grid">
        {schema.widgets.map((widget) => {
          const data = dataByWidget[widget.id] ?? null;
          const span = Math.min(4, Math.max(1, widget.col_span));

          return (
            <div key={widget.id} className={`df-widget-span-${span}`}>
              {widget.type === "kpi" && (
                <KpiCard widget={widget} data={data} loading={loading} />
              )}
              {widget.type === "bar_chart" && (
                <BarChartWidget widget={widget} data={data} loading={loading} />
              )}
              {widget.type === "line_chart" && (
                <LineChartWidget widget={widget} data={data} loading={loading} />
              )}
              {widget.type === "pie_chart" && (
                <PieChartWidget widget={widget} data={data} loading={loading} />
              )}
              {widget.type === "table" && (
                <DataTableWidget widget={widget} data={data} loading={loading} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

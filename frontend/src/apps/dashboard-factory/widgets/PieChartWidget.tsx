import { AlertCircle, Loader2 } from "lucide-react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { WidgetData, WidgetDef } from "../types";

const COLORS = [
  "#7c3aed", "#a855f7", "#06b6d4", "#10b981", "#f59e0b",
  "#ef4444", "#3b82f6", "#ec4899", "#84cc16", "#f97316",
];

type Props = {
  widget: WidgetDef;
  data: WidgetData | null;
  loading: boolean;
};

export function PieChartWidget({ widget, data, loading }: Props) {
  const nameKey = widget.x_field ?? (data?.columns[0] ?? "name");
  const valueKey = widget.y_field ?? (data?.columns[1] ?? "value");
  const chartData = data
    ? data.rows.map((row) => ({ name: String(row[0]), value: Number(row[1]) || 0 }))
    : [];

  return (
    <div className="df-widget-card df-chart-card">
      <span className="df-widget-title">{widget.title}</span>
      {loading ? (
        <div className="df-widget-loading">
          <Loader2 size={20} className="df-spin" />
        </div>
      ) : data?.error ? (
        <div className="df-widget-error">
          <AlertCircle size={14} />
          <span>{data.error}</span>
        </div>
      ) : chartData.length === 0 ? (
        <div className="df-widget-empty">Sin datos</div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="45%"
              outerRadius={85}
              dataKey="value"
              nameKey="name"
              label={({ name, percent }) =>
                `${String(name).slice(0, 10)} ${((percent ?? 0) * 100).toFixed(0)}%`
              }
              labelLine={false}
            >
              {chartData.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ borderRadius: 8, border: "1px solid #dde5ec", fontSize: 12 }}
              formatter={(v) => [String(v), valueKey]}
            />
            <Legend
              iconSize={10}
              wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
              formatter={(v) => String(v).slice(0, 18)}
            />
          </PieChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

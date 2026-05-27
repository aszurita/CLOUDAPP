import { AlertCircle, Loader2 } from "lucide-react";

import type { WidgetData, WidgetDef } from "../types";

type Props = {
  widget: WidgetDef;
  data: WidgetData | null;
  loading: boolean;
};

export function DataTableWidget({ widget, data, loading }: Props) {
  return (
    <div className="df-widget-card df-table-card">
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
      ) : !data || data.rows.length === 0 ? (
        <div className="df-widget-empty">Sin datos</div>
      ) : (
        <div className="df-data-table-wrap">
          <table className="df-data-table">
            <thead>
              <tr>
                {data.columns.map((col) => (
                  <th key={col}>{col.replace(/_/g, " ")}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td key={ci}>{cell === null || cell === undefined ? "—" : String(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

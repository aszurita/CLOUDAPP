import type { SentinelMetricPoint } from "../../api/sentinel";

type Props = {
  points: SentinelMetricPoint[];
};

function valueOf(point: SentinelMetricPoint, key: keyof SentinelMetricPoint) {
  const value = point[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

export function MetricsTimeline({ points }: Props) {
  const recent = points.slice(-36);
  const maxActive = Math.max(1, ...recent.map((point) => valueOf(point, "active_sessions")));
  const maxLocks = Math.max(1, ...recent.map((point) => valueOf(point, "lock_waiting_sessions")));

  return (
    <section className="panel sentinel-timeline-panel">
      <div className="panel-heading">
        <h2>Timeline operativo</h2>
        <span>{recent.length} puntos</span>
      </div>
      <div className="sentinel-timeline">
        {recent.map((point, index) => {
          const activeHeight = Math.max(4, (valueOf(point, "active_sessions") / maxActive) * 100);
          const lockHeight = Math.max(3, (valueOf(point, "lock_waiting_sessions") / maxLocks) * 100);
          const label = point.collected_at ? new Date(point.collected_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
          return (
            <div className="sentinel-timeline-bar" key={`${point.collected_at ?? "point"}-${index}`} title={label}>
              <span className="active" style={{ height: `${activeHeight}%` }} />
              <span className="locks" style={{ height: `${lockHeight}%` }} />
            </div>
          );
        })}
      </div>
      <div className="sentinel-legend">
        <span><i className="active" /> sesiones activas</span>
        <span><i className="locks" /> lock waits</span>
      </div>
    </section>
  );
}

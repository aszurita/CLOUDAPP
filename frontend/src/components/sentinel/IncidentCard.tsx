import { Clock, Database } from "lucide-react";

import type { SentinelIncident } from "../../api/sentinel";
import { SeverityBadge } from "./SeverityBadge";

type Props = {
  incident: SentinelIncident;
  active?: boolean;
  onSelect?: (incident: SentinelIncident) => void;
};

export function IncidentCard({ incident, active, onSelect }: Props) {
  return (
    <button className={`sentinel-incident-card${active ? " active" : ""}`} onClick={() => onSelect?.(incident)}>
      <span className="sentinel-incident-main">
        <strong>{(incident.incident_type ?? "unknown").replace(/_/g, " ")}</strong>
        <small>
          <Database size={13} />
          {incident.database_name ?? "core_banking_sim"}
        </small>
      </span>
      <span className="sentinel-incident-meta">
        <SeverityBadge value={incident.impact_level ?? "low"} />
        <small>
          <Clock size={13} />
          {new Date(incident.detected_at).toLocaleString()}
        </small>
      </span>
    </button>
  );
}

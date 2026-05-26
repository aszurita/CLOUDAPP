import type { CSSProperties } from "react";
import { Activity, ShieldAlert } from "lucide-react";

import type { SentinelPrediction } from "../../api/sentinel";
import { SeverityBadge } from "./SeverityBadge";

type Props = {
  prediction: SentinelPrediction | null;
};

export function RiskScoreCard({ prediction }: Props) {
  const score = prediction?.risk_score ?? 0;
  const pct = Math.round(score * 100);
  const ringStyle = { "--risk": `${pct}%` } as CSSProperties;
  const predictedType = prediction?.predicted_incident_type ?? "none";
  const hasIncident = Boolean(score >= 0.7 || prediction?.has_predicted_incident);
  const displayType = predictedType !== "none" ? predictedType.replace(/_/g, " ") : "riesgo alto sin clasificar";
  const horizon = prediction?.horizon_minutes ?? 10;

  return (
    <section className="panel sentinel-risk-panel">
      <div className="panel-heading">
        <h2>Riesgo de incidente</h2>
        <SeverityBadge value={hasIncident ? prediction?.impact_level ?? "high" : "stable"} />
      </div>
      <div className="sentinel-risk-layout">
        <div className="sentinel-risk-ring" style={ringStyle}>
          <div>
            <strong>{pct}%</strong>
            <span>{horizon} min</span>
          </div>
        </div>
        <div className="sentinel-risk-copy">
          <p className="eyebrow">Predicción principal</p>
          <h3>{hasIncident ? displayType : "Operación estable"}</h3>
          <p>
            {hasIncident
              ? `Posible incidente en los próximos ${horizon} minutos`
              : `Sin incidente probable en los próximos ${horizon} minutos`}
          </p>
          <div className="sentinel-risk-meta">
            {hasIncident ? <ShieldAlert size={16} /> : <Activity size={16} />}
            <span>{prediction?.model_version ? `modelo ${prediction.model_version}` : "modelo cargado"}</span>
          </div>
        </div>
      </div>
    </section>
  );
}

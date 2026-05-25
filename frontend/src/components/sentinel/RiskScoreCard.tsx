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

  return (
    <section className="panel sentinel-risk-panel">
      <div className="panel-heading">
        <h2>Risk Score</h2>
        <SeverityBadge value={prediction?.impact_level ?? "low"} />
      </div>
      <div className="sentinel-risk-layout">
        <div className="sentinel-risk-ring" style={ringStyle}>
          <div>
            <strong>{pct}%</strong>
            <span>{prediction?.horizon_minutes ?? 10} min</span>
          </div>
        </div>
        <div className="sentinel-risk-copy">
          <p className="eyebrow">Predicción</p>
          <h3>{(prediction?.predicted_incident_type ?? "none").replace(/_/g, " ")}</h3>
          <p>{prediction?.has_predicted_incident ? "Incidente probable" : "Sin incidente inminente"}</p>
          <div className="sentinel-risk-meta">
            {prediction?.has_predicted_incident ? <ShieldAlert size={16} /> : <Activity size={16} />}
            <span>{prediction?.model_version ? `modelo ${prediction.model_version}` : "modelo cargado"}</span>
          </div>
        </div>
      </div>
    </section>
  );
}

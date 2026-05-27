from pathlib import Path

from app.schemas.cloudops_autopilot import CloudOpsAzureSnapshot
from app.services.cloudops_autopilot import CloudOpsAutopilotService


def test_cloudops_autopilot_discovers_ready_generated_app(tmp_path: Path) -> None:
    app_dir = tmp_path / "inventory-cloud-app-20260527-120000"
    (app_dir / "backend" / "app").mkdir(parents=True)
    (app_dir / "frontend" / "src").mkdir(parents=True)
    (app_dir / "infra" / "terraform").mkdir(parents=True)
    (app_dir / ".github" / "workflows").mkdir(parents=True)
    (app_dir / "scripts").mkdir(parents=True)
    (app_dir / "backend" / "app" / "main.py").write_text("from fastapi import FastAPI\n", encoding="utf-8")
    (app_dir / "frontend" / "src" / "App.tsx").write_text("export default function App() { return null }\n", encoding="utf-8")
    (app_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (app_dir / "infra" / "terraform" / "main.tf").write_text("resource_group = true\n", encoding="utf-8")
    (app_dir / ".github" / "workflows" / "deploy-azure-container-apps.yml").write_text("name: deploy\n", encoding="utf-8")
    (app_dir / "scripts" / "deploy-azure.ps1").write_text("Write-Host deploy\n", encoding="utf-8")
    (app_dir / "README.md").write_text("# Inventory Cloud App\n\n- Frontend Azure: https://app.example.com\n", encoding="utf-8")

    service = CloudOpsAutopilotService()
    service.generated_root = tmp_path

    apps = service.list_generated_apps()

    assert len(apps) == 1
    assert apps[0].name == "Inventory Cloud App"
    assert apps[0].slug == "inventory-cloud-app"
    assert apps[0].status == "ready"
    assert apps[0].readiness_score == 100
    assert apps[0].azure_links == ["https://app.example.com"]


def test_cloudops_autopilot_plan_blocks_without_selected_app() -> None:
    service = CloudOpsAutopilotService()

    plan = service.plan(None, CloudOpsAzureSnapshot(authenticated=False))

    assert plan.app_id is None
    assert plan.readiness_score == 0
    assert plan.steps[0].status == "blocked"


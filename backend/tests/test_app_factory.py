from pathlib import Path

from app.schemas.app_factory import AppFactoryGenerateRequest, AppFactoryPlanRequest
from app.services.app_factory import AppFactoryService


def test_app_factory_plan_detects_inventory_modules() -> None:
    service = AppFactoryService()

    plan = service.plan(
        AppFactoryPlanRequest(
            prompt="Crea una app de inventario con clientes, productos y ordenes",
            project_name="inventory-cloud-app",
        )
    )

    assert plan.slug == "inventory-cloud-app"
    assert {entity.route for entity in plan.entities} == {"clientes", "productos", "ordenes"}
    assert any(resource.type == "Azure Container App" for resource in plan.resources)
    assert "infra/terraform/main.tf" in plan.files_preview


def test_app_factory_generate_creates_cloud_ready_scaffold(tmp_path: Path) -> None:
    service = AppFactoryService()
    service.generated_root = tmp_path

    response = service.generate(
        AppFactoryGenerateRequest(
            prompt="Crea una app de inventario con clientes, productos y ordenes",
            project_name="inventory-cloud-app",
            initialize_git=False,
        )
    )

    project_path = Path(response.project_path)
    assert response.status == "success"
    assert (project_path / "backend" / "app" / "main.py").exists()
    assert (project_path / "frontend" / "src" / "App.tsx").exists()
    assert (project_path / ".github" / "workflows" / "deploy-azure-container-apps.yml").exists()
    assert (project_path / "infra" / "terraform" / "main.tf").exists()
    assert "azurerm_container_app" in (project_path / "infra" / "terraform" / "main.tf").read_text()
    assert any(link.label == "API Docs" for link in response.links)


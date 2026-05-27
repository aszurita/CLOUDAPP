from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import textwrap
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from pprint import pformat
from uuid import uuid4

from app.core.paths import find_backend_root
from app.schemas.app_factory import (
    AppFactoryArtifact,
    AppFactoryCapability,
    AppFactoryEntity,
    AppFactoryField,
    AppFactoryGenerateRequest,
    AppFactoryGenerateResponse,
    AppFactoryLink,
    AppFactoryPlanRequest,
    AppFactoryPlanResponse,
    AppFactoryResource,
    AppFactoryStatusResponse,
    AppFactoryStep,
)


class AppFactoryService:
    """Generates complete app scaffolds from safe, deterministic templates."""

    def __init__(self) -> None:
        self.backend_root = find_backend_root()
        self.project_root = self.backend_root.parent
        self.generated_root = self.project_root / "generated-apps"

    def status(self) -> AppFactoryStatusResponse:
        return AppFactoryStatusResponse(
            title="AI Cloud App Factory",
            mode="local-generator",
            generated_root=str(self.generated_root),
            supported_frontends=["React + Vite"],
            supported_backends=["FastAPI"],
            supported_databases=["PostgreSQL"],
            supported_clouds=["Azure Container Apps"],
            capabilities=[
                self._capability("git", "Git local repository initialization"),
                self._capability("docker", "Docker image build/push"),
                self._capability("terraform", "Terraform Azure templates"),
                self._capability("az", "Azure CLI available for manual deployment"),
                self._capability("gh", "GitHub CLI available for remote repo creation"),
                self._github_auth_capability(),
                self._azure_auth_capability(),
            ],
        )

    def plan(self, request: AppFactoryPlanRequest) -> AppFactoryPlanResponse:
        project_name = (request.project_name or self._infer_project_name(request.prompt)).strip()
        slug = self._slugify(project_name)
        entities = self._infer_entities(request.prompt)
        resources = [
            AppFactoryResource(
                name=f"rg-{slug}-dev",
                type="Azure Resource Group",
                purpose="Agrupa todos los recursos del ambiente dev.",
                provisioner="Terraform",
            ),
            AppFactoryResource(
                name=f"acr{self._compact_slug(slug)}dev",
                type="Azure Container Registry",
                purpose="Almacena imagenes Docker de frontend y API.",
                provisioner="Terraform + GitHub Actions",
            ),
            AppFactoryResource(
                name=f"cae-{slug}-dev",
                type="Azure Container Apps Environment",
                purpose="Ejecuta los contenedores de la aplicacion.",
                provisioner="Terraform",
            ),
            AppFactoryResource(
                name=f"ca-{slug}-api",
                type="Azure Container App",
                purpose="Backend FastAPI con OpenAPI en /docs.",
                provisioner="Terraform + GitHub Actions",
            ),
            AppFactoryResource(
                name=f"ca-{slug}-web",
                type="Azure Container App",
                purpose="Frontend React publicado por Nginx.",
                provisioner="Terraform + GitHub Actions",
            ),
            AppFactoryResource(
                name=f"psql-{slug}-dev",
                type="Azure Database for PostgreSQL Flexible Server",
                purpose="Persistencia transaccional de la app generada.",
                provisioner="Terraform",
            ),
            AppFactoryResource(
                name=f"kv{self._key_vault_slug(slug)}dev",
                type="Azure Key Vault",
                purpose="Gestiona secretos de conexion y despliegue.",
                provisioner="Terraform",
            ),
        ]
        return AppFactoryPlanResponse(
            project_name=project_name,
            slug=slug,
            summary=(
                f"Se generara una aplicacion CRUD cloud-native para {len(entities)} modulo(s), "
                "con frontend React, API FastAPI, PostgreSQL, Docker, GitHub Actions y Terraform para Azure."
            ),
            frontend=request.frontend,
            backend=request.backend,
            database=request.database,
            auth=request.auth,
            cloud=request.cloud,
            entities=entities,
            resources=resources,
            steps=self._planned_steps(),
            files_preview=[
                "backend/app/main.py",
                "backend/requirements.txt",
                "frontend/src/App.tsx",
                "frontend/src/styles.css",
                "docker-compose.yml",
                ".github/workflows/deploy-azure-container-apps.yml",
                "infra/terraform/main.tf",
                "docs/architecture.md",
                "README.md",
            ],
            estimated_cost_tier="bajo/medio segun replicas, PostgreSQL y retencion de logs",
            guardrails=[
                "El despliegue Azure solo se ejecuta si activas la opcion de despliegue.",
                "GitHub se publica como repositorio privado por defecto y requiere credenciales locales.",
                "Los secretos se parametrizan; no se escriben claves reales en archivos.",
                "Terraform reutiliza un Container Apps Environment existente si Azure ya alcanzo el limite regional.",
                "PostgreSQL usa una region separada para evitar restricciones de oferta en eastus.",
                "La app generada funciona localmente con Docker Compose antes del despliegue cloud.",
            ],
        )

    def generate(self, request: AppFactoryGenerateRequest) -> AppFactoryGenerateResponse:
        plan = self.plan(request)
        if request.deploy_azure:
            unique_slug = self._unique_external_slug(plan.slug)
            if unique_slug != plan.slug:
                plan = self.plan(request.model_copy(update={"project_name": unique_slug}))
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        project_dir = self.generated_root / f"{plan.slug}-{timestamp}"
        self.generated_root.mkdir(parents=True, exist_ok=True)
        project_dir.mkdir(parents=True, exist_ok=False)

        files = self._render_files(plan)
        for relative_path, content in files.items():
            self._write_file(project_dir / relative_path, content)

        self._format_terraform(project_dir)

        deployment_links: dict[str, str] = {}
        operation_steps: list[AppFactoryStep] = []
        response_status: str = "success"
        github_preflight_blocked = False

        if request.publish_github and not self._github_credentials(request.github_token):
            response_status = "partial"
            github_preflight_blocked = True
            operation_steps.append(
                AppFactoryStep(
                    name="Publicar GitHub",
                    status="blocked",
                    detail="GitHub no esta conectado. Pega un token con permisos repo + workflow, define GITHUB_TOKEN o ejecuta gh auth login.",
                )
            )

        if request.deploy_azure and not github_preflight_blocked:
            try:
                deployment_links = self._deploy_azure(project_dir)
                self._write_public_links(project_dir, github_url=None, deployment_links=deployment_links)
                operation_steps.append(
                    AppFactoryStep(
                        name="Desplegar Azure",
                        status="success",
                        detail="Infraestructura, backend y frontend desplegados en Azure Container Apps.",
                    )
                )
            except Exception as exc:
                response_status = "partial"
                operation_steps.append(
                    AppFactoryStep(name="Desplegar Azure", status="blocked", detail=self._safe_error(exc))
                )
        elif request.deploy_azure and github_preflight_blocked:
            operation_steps.append(
                AppFactoryStep(
                    name="Desplegar Azure",
                    status="skipped",
                    detail="Se omitio Azure porque solicitaste GitHub + Azure y GitHub no estaba autenticado.",
                )
            )

        git_available = shutil.which("git") is not None
        git_initialized = False
        github_url: str | None = None

        if request.publish_github and not github_preflight_blocked:
            try:
                github_url = self._publish_github(
                    project_dir,
                    plan.slug,
                    private=request.github_private,
                    deployment_links=deployment_links,
                    token_override=request.github_token,
                )
                git_initialized = True
                operation_steps.append(
                    AppFactoryStep(
                        name="Publicar GitHub",
                        status="success",
                        detail=f"Repositorio publicado en {github_url}.",
                    )
                )
            except Exception as exc:
                response_status = "partial"
                if request.initialize_git and git_available:
                    git_initialized = self._init_git(project_dir)
                operation_steps.append(
                    AppFactoryStep(name="Publicar GitHub", status="blocked", detail=self._safe_error(exc))
                )
        elif request.initialize_git and git_available:
            git_initialized = self._init_git(project_dir)

        local_web_port = 5178
        local_api_port = 8080
        steps = self._success_steps(git_initialized=git_initialized, git_requested=request.initialize_git)
        steps.extend(operation_steps)
        artifacts = [
            AppFactoryArtifact(label="Proyecto generado", path=str(project_dir), kind="project"),
            AppFactoryArtifact(label="Backend FastAPI", path=str(project_dir / "backend"), kind="backend"),
            AppFactoryArtifact(label="Frontend React", path=str(project_dir / "frontend"), kind="frontend"),
            AppFactoryArtifact(
                label="Terraform Azure",
                path=str(project_dir / "infra" / "terraform"),
                kind="terraform",
            ),
            AppFactoryArtifact(
                label="GitHub Actions",
                path=str(project_dir / ".github" / "workflows" / "deploy-azure-container-apps.yml"),
                kind="workflow",
            ),
            AppFactoryArtifact(label="Documentacion", path=str(project_dir / "docs"), kind="documentation"),
        ]
        links = [
            AppFactoryLink(label="Carpeta del proyecto", url=str(project_dir), kind="file"),
            AppFactoryLink(label="Frontend local", url=f"http://localhost:{local_web_port}", kind="local"),
            AppFactoryLink(label="API local", url=f"http://localhost:{local_api_port}", kind="local"),
            AppFactoryLink(label="API Docs", url=f"http://localhost:{local_api_port}/docs", kind="local"),
            AppFactoryLink(
                label="Terraform",
                url=str(project_dir / "infra" / "terraform"),
                kind="cloud-template",
            ),
            AppFactoryLink(
                label="Workflow GitHub Actions",
                url=str(project_dir / ".github" / "workflows" / "deploy-azure-container-apps.yml"),
                kind="github-template",
            ),
        ]
        if github_url:
            links.append(AppFactoryLink(label="Repositorio GitHub", url=github_url, kind="github"))
        if deployment_links.get("web_url"):
            links.append(AppFactoryLink(label="Frontend Azure", url=deployment_links["web_url"], kind="azure"))
        if deployment_links.get("api_url"):
            links.append(AppFactoryLink(label="API Azure", url=deployment_links["api_url"], kind="azure"))
        if deployment_links.get("api_docs_url"):
            links.append(AppFactoryLink(label="API Docs Azure", url=deployment_links["api_docs_url"], kind="azure"))
        commands = [
            f"cd {project_dir}",
            "docker compose up --build",
            ".\\scripts\\deploy-azure.ps1",
            "cd infra/terraform",
            "copy terraform.tfvars.example terraform.tfvars",
            "terraform init",
            "terraform plan",
            "terraform apply -auto-approve",
        ]
        message = "Proyecto generado con plantillas controladas."
        if request.publish_github and github_url:
            message += " Publicado en GitHub."
        if request.deploy_azure and deployment_links:
            message += " Desplegado en Azure con frontend y backend reales."
        if response_status == "partial":
            message += " Algunas operaciones externas quedaron bloqueadas; revisa el timeline."
        return AppFactoryGenerateResponse(
            job_id=str(uuid4()),
            status=response_status,
            message=message,
            project_name=plan.project_name,
            slug=plan.slug,
            project_path=str(project_dir),
            generated_at=datetime.now(timezone.utc),
            links=links,
            artifacts=artifacts,
            steps=steps,
            commands=commands,
            plan=plan,
        )

    def _capability(self, command: str, detail: str) -> AppFactoryCapability:
        available = shutil.which(command) is not None
        suffix = "disponible" if available else "no instalado"
        return AppFactoryCapability(name=command, available=available, detail=f"{detail}: {suffix}.")

    def _github_auth_capability(self) -> AppFactoryCapability:
        credentials = self._github_credentials()
        if credentials:
            return AppFactoryCapability(
                name="github-auth",
                available=True,
                detail=f"GitHub conectado como {credentials['login']}.",
            )
        return AppFactoryCapability(
            name="github-auth",
            available=False,
            detail="GitHub no conectado. Usa GITHUB_TOKEN, gh auth login o pega un token al publicar.",
        )

    def _azure_auth_capability(self) -> AppFactoryCapability:
        az_path = shutil.which("az")
        if az_path is None:
            return AppFactoryCapability(name="azure-auth", available=False, detail="Azure CLI no instalado.")
        args = ["az", "account", "show", "--query", "user.name", "-o", "tsv"]
        try:
            completed = subprocess.run(
                " ".join(args) if az_path.lower().endswith((".cmd", ".bat")) else args,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
                shell=az_path.lower().endswith((".cmd", ".bat")),
            )
        except Exception:
            return AppFactoryCapability(name="azure-auth", available=False, detail="No se pudo consultar Azure CLI.")
        user = completed.stdout.strip()
        if completed.returncode == 0 and user:
            return AppFactoryCapability(name="azure-auth", available=True, detail=f"Azure conectado como {user}.")
        return AppFactoryCapability(name="azure-auth", available=False, detail="Azure no conectado. Ejecuta az login.")

    def _planned_steps(self) -> list[AppFactoryStep]:
        return [
            AppFactoryStep(name="Analizar prompt", status="pending", detail="Detectar modulos, stack y alcance."),
            AppFactoryStep(name="Generar backend", status="pending", detail="Crear FastAPI, CRUD, healthcheck y OpenAPI."),
            AppFactoryStep(name="Generar frontend", status="pending", detail="Crear React + Vite con UI CRUD."),
            AppFactoryStep(name="Configurar Docker", status="pending", detail="Crear Dockerfiles y docker-compose."),
            AppFactoryStep(name="Crear CI/CD", status="pending", detail="Crear workflow de GitHub Actions para Azure."),
            AppFactoryStep(name="Crear Terraform", status="pending", detail="Crear infraestructura Azure Container Apps."),
            AppFactoryStep(name="Documentar", status="pending", detail="Crear README y guias de despliegue."),
            AppFactoryStep(name="Publicar GitHub", status="pending", detail="Crear repo privado y hacer push si se solicita."),
            AppFactoryStep(name="Desplegar Azure", status="pending", detail="Aplicar Terraform y publicar frontend/backend si se solicita."),
        ]

    def _success_steps(self, *, git_initialized: bool, git_requested: bool) -> list[AppFactoryStep]:
        steps = [
            ("Analizar prompt", "success", "Plan tecnico generado."),
            ("Generar backend", "success", "FastAPI CRUD creado."),
            ("Generar frontend", "success", "React + Vite creado."),
            ("Configurar Docker", "success", "Dockerfiles y compose creados."),
            ("Crear CI/CD", "success", "Workflow Azure Container Apps creado."),
            ("Crear Terraform", "success", "Infraestructura Azure parametrizada."),
            ("Documentar", "success", "README y docs creados."),
        ]
        result = [AppFactoryStep(name=name, status=status, detail=detail) for name, status, detail in steps]
        if git_requested:
            result.append(
                AppFactoryStep(
                    name="Inicializar Git",
                    status="success" if git_initialized else "skipped",
                    detail="Repositorio local inicializado." if git_initialized else "Git no disponible o commit omitido.",
                )
            )
        return result

    def _infer_project_name(self, prompt: str) -> str:
        text = prompt.lower()
        if "inventario" in text:
            return "inventory-cloud-app"
        if "cliente" in text:
            return "customer-cloud-app"
        if "proveedor" in text:
            return "supplier-cloud-app"
        if "orden" in text or "compra" in text:
            return "procurement-cloud-app"
        return "ai-generated-cloud-app"

    def _infer_entities(self, prompt: str) -> list[AppFactoryEntity]:
        text = prompt.lower()
        catalog = {
            "clientes": AppFactoryEntity(
                name="clientes",
                route="clientes",
                display_name="Clientes",
                fields=[
                    AppFactoryField(name="nombre", label="Nombre", type="text"),
                    AppFactoryField(name="email", label="Email", type="email"),
                    AppFactoryField(name="telefono", label="Telefono", type="text", required=False),
                    AppFactoryField(name="estado", label="Estado", type="status"),
                ],
            ),
            "productos": AppFactoryEntity(
                name="productos",
                route="productos",
                display_name="Productos",
                fields=[
                    AppFactoryField(name="sku", label="SKU", type="text"),
                    AppFactoryField(name="nombre", label="Nombre", type="text"),
                    AppFactoryField(name="precio", label="Precio", type="currency"),
                    AppFactoryField(name="stock", label="Stock", type="number"),
                ],
            ),
            "ordenes": AppFactoryEntity(
                name="ordenes",
                route="ordenes",
                display_name="Ordenes",
                fields=[
                    AppFactoryField(name="codigo", label="Codigo", type="text"),
                    AppFactoryField(name="cliente", label="Cliente", type="text"),
                    AppFactoryField(name="estado", label="Estado", type="status"),
                    AppFactoryField(name="total", label="Total", type="currency"),
                ],
            ),
            "proveedores": AppFactoryEntity(
                name="proveedores",
                route="proveedores",
                display_name="Proveedores",
                fields=[
                    AppFactoryField(name="razon_social", label="Razon social", type="text"),
                    AppFactoryField(name="contacto", label="Contacto", type="text"),
                    AppFactoryField(name="email", label="Email", type="email"),
                    AppFactoryField(name="estado", label="Estado", type="status"),
                ],
            ),
        }
        selected: list[AppFactoryEntity] = []
        keyword_map = {
            "clientes": ["cliente", "clientes", "customer", "customers"],
            "productos": ["producto", "productos", "inventario", "stock", "inventory"],
            "ordenes": ["orden", "ordenes", "pedido", "pedidos", "compra", "purchase"],
            "proveedores": ["proveedor", "proveedores", "supplier", "suppliers"],
        }
        for key, keywords in keyword_map.items():
            if any(keyword in text for keyword in keywords):
                selected.append(catalog[key])
        if not selected:
            selected = [catalog["clientes"], catalog["productos"], catalog["ordenes"]]
        return selected

    def _slugify(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
        return slug[:24].strip("-") or "generated-app"

    def _compact_slug(self, value: str) -> str:
        compact = re.sub(r"[^a-z0-9]", "", value.lower())
        return compact[:18] or "generatedapp"

    def _key_vault_slug(self, value: str) -> str:
        compact = re.sub(r"[^a-z0-9]", "", value.lower())
        return compact[:16] or "generatedapp"

    def _unique_external_slug(self, slug: str) -> str:
        candidate = slug
        for _ in range(3):
            if not self._azure_slug_conflicts(candidate):
                return candidate
            suffix = datetime.now(timezone.utc).strftime("%d%H%M")
            base = candidate[:17].rstrip("-") or "generated-app"
            candidate = f"{base}-{suffix}"[:24].strip("-")
        return candidate

    def _azure_slug_conflicts(self, slug: str) -> bool:
        if shutil.which("az") is None:
            return False
        checks = [
            ["az", "group", "exists", "--name", f"rg-{slug}-dev"],
            [
                "az",
                "containerapp",
                "show",
                "--resource-group",
                "rg-cloudapp-dev",
                "--name",
                f"ca-{slug}-api",
                "--query",
                "name",
                "-o",
                "tsv",
            ],
            [
                "az",
                "containerapp",
                "show",
                "--resource-group",
                "rg-cloudapp-dev",
                "--name",
                f"ca-{slug}-web",
                "--query",
                "name",
                "-o",
                "tsv",
            ],
        ]
        for command in checks:
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
            except Exception:
                continue
            if command[1:3] == ["group", "exists"] and completed.stdout.strip().lower() == "true":
                return True
            if command[1:3] == ["containerapp", "show"] and completed.returncode == 0 and completed.stdout.strip():
                return True
        return False

    def _existing_container_app_environment(self) -> dict[str, str] | None:
        az_path = shutil.which("az")
        if az_path is None:
            return None
        args = [
            "az",
            "containerapp",
            "env",
            "list",
            "--query",
            "[0].{id:id,name:name,resourceGroup:resourceGroup,location:location}",
            "-o",
            "json",
        ]
        try:
            completed = subprocess.run(
                " ".join(args) if az_path.lower().endswith((".cmd", ".bat")) else args,
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
                shell=az_path.lower().endswith((".cmd", ".bat")),
            )
        except Exception:
            return None
        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict) or not payload.get("id"):
            return None
        return {key: str(value or "") for key, value in payload.items()}

    def _github_credentials(self, token_override: str | None = None) -> dict[str, str] | None:
        token = (
            (token_override or "").strip()
            or os.getenv("GITHUB_TOKEN")
            or os.getenv("GH_TOKEN")
            or self._github_token_from_gh()
            or self._github_token_from_git_credentials()
        )
        if not token:
            return None
        try:
            user = self._github_api("GET", "/user", token)
        except Exception:
            return None
        login = str(user.get("login") or "").strip()
        if not login:
            return None
        return {"login": login, "token": token}

    def _github_token_from_gh(self) -> str | None:
        if shutil.which("gh") is None:
            return None
        try:
            completed = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except Exception:
            return None
        token = completed.stdout.strip()
        return token if completed.returncode == 0 and token else None

    def _github_token_from_git_credentials(self) -> str | None:
        if shutil.which("git") is None:
            return None
        try:
            completed = subprocess.run(
                ["git", "credential", "fill"],
                input="protocol=https\nhost=github.com\n\n",
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                env={
                    **dict(os.environ),
                    "GIT_TERMINAL_PROMPT": "0",
                    "GCM_INTERACTIVE": "Never",
                },
            )
        except Exception:
            return None
        if completed.returncode != 0:
            return None
        for line in completed.stdout.splitlines():
            if line.startswith("password="):
                token = line.removeprefix("password=").strip()
                return token or None
        return None

    def _github_api(self, method: str, path: str, token: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        data = None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-cloud-app-factory",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"https://api.github.com{path}", data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}

    def _github_repo_exists(self, login: str, repo_name: str, token: str) -> bool:
        try:
            self._github_api("GET", f"/repos/{login}/{repo_name}", token)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise

    def _create_github_repo(self, preferred_name: str, private: bool, token_override: str | None = None) -> tuple[str, str, str]:
        credentials = self._github_credentials(token_override)
        if not credentials:
            raise RuntimeError("GitHub no esta conectado. Pega un token en la pantalla, define GITHUB_TOKEN o ejecuta gh auth login.")

        login = credentials["login"]
        token = credentials["token"]
        base_name = self._slugify(preferred_name)[:80]
        candidate = base_name
        if self._github_repo_exists(login, candidate, token):
            suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            candidate = f"{base_name[:84]}-{suffix}"

        repo = self._github_api(
            "POST",
            "/user/repos",
            token,
            {
                "name": candidate,
                "private": private,
                "description": "Cloud-native app generated by AI Cloud App Factory",
                "auto_init": False,
            },
        )
        html_url = str(repo.get("html_url") or f"https://github.com/{login}/{candidate}")
        clone_url = str(repo.get("clone_url") or f"https://github.com/{login}/{candidate}.git")
        return html_url, clone_url, token

    def _publish_github(
        self,
        project_dir: Path,
        slug: str,
        *,
        private: bool,
        deployment_links: dict[str, str],
        token_override: str | None = None,
    ) -> str:
        html_url, clone_url, token = self._create_github_repo(slug, private=private, token_override=token_override)
        self._write_public_links(project_dir, github_url=html_url, deployment_links=deployment_links)

        if not self._init_git(project_dir):
            raise RuntimeError("No se pudo inicializar Git local.")
        self._ensure_git_identity(project_dir)
        self._run_git(["remote", "remove", "origin"], project_dir, allow_failure=True)
        self._run_git(["remote", "add", "origin", clone_url], project_dir)
        self._run_git(["add", "."], project_dir)
        commit = self._run_git(["commit", "-m", "Initial cloud app deployment"], project_dir, allow_failure=True)
        if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr).lower():
            raise RuntimeError(self._tail(commit.stderr or commit.stdout))
        self._run_git(["branch", "-M", "main"], project_dir)
        push_url = clone_url.replace("https://", f"https://x-access-token:{token}@")
        self._run_git(
            [
                "-c",
                "credential.helper=",
                "push",
                "-u",
                push_url,
                "main:main",
            ],
            project_dir,
            mask=token,
        )
        return html_url

    def _deploy_azure(self, project_dir: Path) -> dict[str, str]:
        missing = [tool for tool in ("az", "terraform", "docker") if shutil.which(tool) is None]
        if missing:
            raise RuntimeError(f"No se puede desplegar en Azure. Faltan herramientas: {', '.join(missing)}.")
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            raise RuntimeError("No se encontro PowerShell para ejecutar scripts/deploy-azure.ps1.")
        script = project_dir / "scripts" / "deploy-azure.ps1"
        completed = subprocess.run(
            [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(self._tail(completed.stderr or completed.stdout))
        outputs = self._terraform_outputs(project_dir)
        if not outputs.get("web_url") or not outputs.get("api_url"):
            outputs.update(self._parse_deploy_output(completed.stdout))
        if not outputs.get("web_url") or not outputs.get("api_url"):
            raise RuntimeError("Azure termino sin devolver URLs publicas de frontend y API.")
        return outputs

    def _terraform_outputs(self, project_dir: Path) -> dict[str, str]:
        terraform_dir = project_dir / "infra" / "terraform"
        try:
            completed = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=terraform_dir,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except Exception:
            return {}
        if completed.returncode != 0 or not completed.stdout.strip():
            return {}
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return {}
        result: dict[str, str] = {}
        for key in ("web_url", "api_url", "api_docs_url", "container_registry_login_server", "resource_group_name"):
            value = payload.get(key, {})
            if isinstance(value, dict) and value.get("value") is not None:
                result[key] = str(value["value"])
        return result

    def _parse_deploy_output(self, output: str) -> dict[str, str]:
        labels = {"Frontend": "web_url", "API": "api_url", "API Docs": "api_docs_url"}
        result: dict[str, str] = {}
        for line in output.splitlines():
            for label, key in labels.items():
                prefix = f"{label}:"
                if line.strip().startswith(prefix):
                    result[key] = line.split(":", 1)[1].strip()
        return result

    def _write_public_links(self, project_dir: Path, *, github_url: str | None, deployment_links: dict[str, str]) -> None:
        rows: list[str] = []
        if github_url:
            rows.append(f"- GitHub: {github_url}")
        if deployment_links.get("web_url"):
            rows.append(f"- Frontend Azure: {deployment_links['web_url']}")
        if deployment_links.get("api_url"):
            rows.append(f"- API Azure: {deployment_links['api_url']}")
        if deployment_links.get("api_docs_url"):
            rows.append(f"- API Docs Azure: {deployment_links['api_docs_url']}")
        if not rows:
            return
        block = "\n## Links publicados\n\n" + "\n".join(rows) + "\n"
        for relative in ("README.md", "docs/azure-deploy.md"):
            path = project_dir / relative
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            marker = "## Links publicados"
            if marker in content:
                content = content.split(marker, 1)[0].rstrip() + block
            else:
                content = content.rstrip() + "\n" + block
            path.write_text(content, encoding="utf-8")

    def _ensure_git_identity(self, project_dir: Path) -> None:
        name = self._run_git(["config", "--get", "user.name"], project_dir, allow_failure=True)
        email = self._run_git(["config", "--get", "user.email"], project_dir, allow_failure=True)
        if name.returncode != 0 or not name.stdout.strip():
            self._run_git(["config", "user.name", "AI Cloud App Factory"], project_dir)
        if email.returncode != 0 or not email.stdout.strip():
            self._run_git(["config", "user.email", "ai-cloud-app-factory@users.noreply.github.com"], project_dir)

    def _run_git(
        self,
        args: list[str],
        project_dir: Path,
        *,
        allow_failure: bool = False,
        mask: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ["git", *args],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env={
                **dict(os.environ),
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "Never",
            },
        )
        if completed.returncode != 0 and not allow_failure:
            message = completed.stderr or completed.stdout or "Git command failed."
            if mask:
                message = message.replace(mask, "***")
            raise RuntimeError(self._tail(message))
        return completed

    def _tail(self, value: str, max_lines: int = 20) -> str:
        lines = [line for line in value.strip().splitlines() if line.strip()]
        return "\n".join(lines[-max_lines:]) if lines else "Operacion externa fallida."

    def _safe_error(self, exc: Exception) -> str:
        return self._tail(str(exc), max_lines=8)

    def _write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")

    def _init_git(self, project_dir: Path) -> bool:
        try:
            subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True, text=True)
            return True
        except Exception:
            return False

    def _format_terraform(self, project_dir: Path) -> None:
        if shutil.which("terraform") is None:
            return
        terraform_dir = project_dir / "infra" / "terraform"
        try:
            subprocess.run(["terraform", "fmt"], cwd=terraform_dir, check=False, capture_output=True, text=True)
        except Exception:
            return

    def _render_files(self, plan: AppFactoryPlanResponse) -> dict[str, str]:
        return {
            ".gitignore": self._gitignore_template(),
            "README.md": self._readme_template(plan),
            "docker-compose.yml": self._docker_compose_template(plan),
            "backend/requirements.txt": self._backend_requirements_template(),
            "backend/Dockerfile": self._backend_dockerfile_template(),
            "backend/app/main.py": self._backend_main_template(plan),
            "frontend/package.json": self._frontend_package_template(plan),
            "frontend/index.html": self._frontend_index_template(plan),
            "frontend/vite.config.ts": self._frontend_vite_template(),
            "frontend/tsconfig.json": self._frontend_tsconfig_template(),
            "frontend/src/App.tsx": self._frontend_app_template(plan),
            "frontend/src/main.tsx": self._frontend_main_template(),
            "frontend/src/vite-env.d.ts": '/// <reference types="vite/client" />',
            "frontend/src/styles.css": self._frontend_styles_template(),
            "frontend/Dockerfile": self._frontend_dockerfile_template(),
            "frontend/nginx.conf": self._frontend_nginx_template(),
            ".github/workflows/deploy-azure-container-apps.yml": self._github_workflow_template(plan),
            "infra/terraform/versions.tf": self._terraform_versions_template(),
            "infra/terraform/main.tf": self._terraform_main_template(plan),
            "infra/terraform/variables.tf": self._terraform_variables_template(),
            "infra/terraform/outputs.tf": self._terraform_outputs_template(),
            "infra/terraform/terraform.tfvars.example": self._terraform_tfvars_template(plan),
            "docs/architecture.md": self._architecture_doc_template(plan),
            "docs/azure-deploy.md": self._azure_doc_template(plan),
            "scripts/local-healthcheck.ps1": self._healthcheck_script_template(),
            "scripts/deploy-azure.ps1": self._azure_deploy_script_template(plan),
        }

    def _gitignore_template(self) -> str:
        return """
        __pycache__/
        *.pyc
        .env
        .env.*
        !.env.example
        node_modules/
        dist/
        .vite/
        *.tsbuildinfo
        .terraform/
        *.tfstate
        *.tfstate.*
        *.tfvars
        !*.tfvars.example
        *.db
        """

    def _readme_template(self, plan: AppFactoryPlanResponse) -> str:
        entities = ", ".join(entity.display_name for entity in plan.entities)
        return f"""
        # {plan.project_name}

        Aplicacion generada por AI Cloud App Factory.

        ## Stack

        - Frontend: {plan.frontend}
        - Backend: {plan.backend}
        - Base de datos: {plan.database}
        - Auth: {plan.auth}
        - Cloud: {plan.cloud}
        - Modulos: {entities}

        ## Ejecutar localmente

        ```powershell
        docker compose up --build
        ```

        Links locales:

        - Frontend: http://localhost:5178
        - API: http://localhost:8080
        - API Docs: http://localhost:8080/docs

        ## Despliegue Azure

        Para desplegar infraestructura, backend y frontend desde esta maquina:

        ```powershell
        .\\scripts\\deploy-azure.ps1
        ```

        Para aplicar solo infraestructura:

        ```powershell
        cd infra/terraform
        copy terraform.tfvars.example terraform.tfvars
        terraform init
        terraform plan
        terraform apply -auto-approve
        ```

        Despues de configurar `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` y `AZURE_SUBSCRIPTION_ID` en GitHub, el workflow `.github/workflows/deploy-azure-container-apps.yml` reconstruye y publica frontend y backend.

        ## Seguridad

        El scaffold no incluye secretos reales. Revisa costos de PostgreSQL, Container Apps, ACR y Log Analytics antes de aplicar Terraform.
        """

    def _docker_compose_template(self, plan: AppFactoryPlanResponse) -> str:
        return f"""
        services:
          postgres:
            image: postgres:16-alpine
            environment:
              POSTGRES_USER: app_user
              POSTGRES_PASSWORD: app_pass
              POSTGRES_DB: appdb
            ports:
              - "55432:5432"
            volumes:
              - pg_data:/var/lib/postgresql/data
            healthcheck:
              test: ["CMD-SHELL", "pg_isready -U app_user -d appdb"]
              interval: 10s
              timeout: 5s
              retries: 5

          api:
            build: ./backend
            environment:
              APP_NAME: "{plan.project_name}"
              DATABASE_URL: "postgresql+psycopg://app_user:app_pass@postgres:5432/appdb"
              FRONTEND_ORIGINS: "http://localhost:5178"
            ports:
              - "8080:8000"
            depends_on:
              postgres:
                condition: service_healthy

          web:
            build:
              context: ./frontend
              args:
                VITE_API_BASE_URL: "http://localhost:8080"
            ports:
              - "5178:80"
            depends_on:
              - api

        volumes:
          pg_data:
        """

    def _backend_requirements_template(self) -> str:
        return """
        fastapi==0.115.0
        uvicorn[standard]==0.30.6
        sqlalchemy==2.0.35
        psycopg[binary]>=3.2,<4.0
        pydantic-settings==2.5.2
        """

    def _backend_dockerfile_template(self) -> str:
        return """
        FROM python:3.12-slim

        WORKDIR /app
        COPY requirements.txt .
        RUN pip install --no-cache-dir -r requirements.txt
        COPY app ./app
        EXPOSE 8000
        CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
        """

    def _backend_main_template(self, plan: AppFactoryPlanResponse) -> str:
        entities_payload = [
            {
                "name": entity.name,
                "route": entity.route,
                "display_name": entity.display_name,
                "fields": [field.model_dump() for field in entity.fields],
            }
            for entity in plan.entities
        ]
        entities_python = pformat(entities_payload, width=120)
        return (
            '''
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, create_engine, func, select


APP_NAME = os.getenv("APP_NAME", "Generated Cloud App")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
FRONTEND_ORIGINS = [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5178").split(",") if origin.strip()]

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
metadata = MetaData()

ENTITY_CONFIG =
'''
            + entities_python
            + '''


def column_for_field(field: dict[str, Any]) -> Column:
    field_type = field["type"]
    if field_type == "number":
        return Column(field["name"], Integer, nullable=not field.get("required", True))
    if field_type == "currency":
        return Column(field["name"], Float, nullable=not field.get("required", True))
    return Column(field["name"], String(255), nullable=not field.get("required", True))


tables: dict[str, Table] = {}
for entity in ENTITY_CONFIG:
    columns = [
        Column("id", Integer, primary_key=True, autoincrement=True),
        *(column_for_field(field) for field in entity["fields"]),
        Column("created_at", DateTime, default=datetime.utcnow, nullable=False),
    ]
    tables[entity["route"]] = Table(entity["route"], metadata, *columns)


class ItemPayload(BaseModel):
    data: dict[str, Any]


app = FastAPI(title=APP_NAME, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    metadata.create_all(engine)
    seed_demo_data()


@app.get("/health")
def health() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(select(1))
    return {"status": "healthy", "database": "connected", "app": APP_NAME}


@app.get("/api/schema")
def schema() -> dict[str, Any]:
    return {"entities": ENTITY_CONFIG}


@app.get("/api/{resource}")
def list_items(resource: str, limit: int = 100) -> list[dict[str, Any]]:
    table = table_or_404(resource)
    with engine.connect() as conn:
        rows = conn.execute(select(table).order_by(table.c.id.desc()).limit(limit)).mappings().all()
    return [row_dict(row) for row in rows]


@app.post("/api/{resource}")
def create_item(resource: str, payload: ItemPayload) -> dict[str, Any]:
    table = table_or_404(resource)
    clean = clean_payload(resource, payload.data)
    with engine.begin() as conn:
        result = conn.execute(table.insert().values(**clean))
        item_id = result.inserted_primary_key[0]
        row = conn.execute(select(table).where(table.c.id == item_id)).mappings().one()
    return row_dict(row)


@app.get("/api/{resource}/{item_id}")
def get_item(resource: str, item_id: int) -> dict[str, Any]:
    table = table_or_404(resource)
    with engine.connect() as conn:
        row = conn.execute(select(table).where(table.c.id == item_id)).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found.")
    return row_dict(row)


@app.put("/api/{resource}/{item_id}")
def update_item(resource: str, item_id: int, payload: ItemPayload) -> dict[str, Any]:
    table = table_or_404(resource)
    clean = clean_payload(resource, payload.data)
    with engine.begin() as conn:
        result = conn.execute(table.update().where(table.c.id == item_id).values(**clean))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found.")
        row = conn.execute(select(table).where(table.c.id == item_id)).mappings().one()
    return row_dict(row)


@app.delete("/api/{resource}/{item_id}")
def delete_item(resource: str, item_id: int) -> dict[str, str]:
    table = table_or_404(resource)
    with engine.begin() as conn:
        result = conn.execute(table.delete().where(table.c.id == item_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Item not found.")
    return {"status": "deleted"}


def table_or_404(resource: str) -> Table:
    table = tables.get(resource)
    if table is None:
        raise HTTPException(status_code=404, detail="Unknown resource.")
    return table


def entity_or_404(resource: str) -> dict[str, Any]:
    for entity in ENTITY_CONFIG:
        if entity["route"] == resource:
            return entity
    raise HTTPException(status_code=404, detail="Unknown resource.")


def clean_payload(resource: str, data: dict[str, Any]) -> dict[str, Any]:
    entity = entity_or_404(resource)
    clean: dict[str, Any] = {}
    for field in entity["fields"]:
        value = data.get(field["name"])
        if value in (None, "") and field.get("required", True):
            value = default_for(field)
        if field["type"] == "number":
            value = int(value or 0)
        elif field["type"] == "currency":
            value = float(value or 0)
        clean[field["name"]] = value
    return clean


def default_for(field: dict[str, Any]) -> Any:
    if field["type"] in {"number", "currency"}:
        return 0
    if field["type"] == "status":
        return "activo"
    return f"demo-{field['name']}"


def row_dict(row: Any) -> dict[str, Any]:
    result = dict(row)
    if isinstance(result.get("created_at"), datetime):
        result["created_at"] = result["created_at"].isoformat()
    return result


def seed_demo_data() -> None:
    with engine.begin() as conn:
        for entity in ENTITY_CONFIG:
            table = tables[entity["route"]]
            count = conn.execute(select(func.count()).select_from(table)).scalar_one()
            if count:
                continue
            first = {field["name"]: demo_value(field, 1) for field in entity["fields"]}
            second = {field["name"]: demo_value(field, 2) for field in entity["fields"]}
            conn.execute(table.insert(), [first, second])


def demo_value(field: dict[str, Any], index: int) -> Any:
    if field["type"] == "email":
        return f"demo{index}@example.com"
    if field["type"] == "number":
        return 10 * index
    if field["type"] == "currency":
        return 99.5 * index
    if field["type"] == "status":
        return "activo" if index == 1 else "revision"
    return f"{field['label']} {index}"
'''
        ).replace("ENTITY_CONFIG =\n", "ENTITY_CONFIG = ")

    def _frontend_package_template(self, plan: AppFactoryPlanResponse) -> str:
        return json.dumps(
            {
                "name": plan.slug,
                "private": True,
                "version": "1.0.0",
                "type": "module",
                "scripts": {"dev": "vite", "build": "tsc -b && vite build", "preview": "vite preview"},
                "dependencies": {
                    "@vitejs/plugin-react": "4.3.3",
                    "vite": "5.4.10",
                    "typescript": "5.6.3",
                    "react": "18.3.1",
                    "react-dom": "18.3.1",
                    "lucide-react": "0.468.0",
                },
                "devDependencies": {"@types/react": "18.3.11", "@types/react-dom": "18.3.1"},
            },
            indent=2,
        )

    def _frontend_index_template(self, plan: AppFactoryPlanResponse) -> str:
        return f"""
        <!doctype html>
        <html lang="es">
          <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>{plan.project_name}</title>
          </head>
          <body>
            <div id="root"></div>
            <script type="module" src="/src/main.tsx"></script>
          </body>
        </html>
        """

    def _frontend_vite_template(self) -> str:
        return """
        import { defineConfig } from "vite";
        import react from "@vitejs/plugin-react";

        export default defineConfig({
          plugins: [react()],
          server: { host: "0.0.0.0", port: 5178 },
        });
        """

    def _frontend_tsconfig_template(self) -> str:
        return """
        {
          "compilerOptions": {
            "target": "ES2020",
            "useDefineForClassFields": true,
            "lib": ["DOM", "DOM.Iterable", "ES2020"],
            "allowJs": false,
            "skipLibCheck": true,
            "esModuleInterop": true,
            "allowSyntheticDefaultImports": true,
            "strict": true,
            "forceConsistentCasingInFileNames": true,
            "module": "ESNext",
            "moduleResolution": "Node",
            "resolveJsonModule": true,
            "isolatedModules": true,
            "noEmit": true,
            "jsx": "react-jsx"
          },
          "include": ["src"],
          "references": []
        }
        """

    def _frontend_main_template(self) -> str:
        return """
        import React from "react";
        import ReactDOM from "react-dom/client";
        import App from "./App";
        import "./styles.css";

        ReactDOM.createRoot(document.getElementById("root")!).render(
          <React.StrictMode>
            <App />
          </React.StrictMode>,
        );
        """

    def _frontend_app_template(self, plan: AppFactoryPlanResponse) -> str:
        entities_payload = [
            {
                "name": entity.name,
                "route": entity.route,
                "display_name": entity.display_name,
                "fields": [field.model_dump() for field in entity.fields],
            }
            for entity in plan.entities
        ]
        entities_json = json.dumps(entities_payload, indent=2)
        title_json = json.dumps(plan.project_name)
        return (
            '''
import { Activity, CheckCircle2, Database, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type Field = {
  name: string;
  label: string;
  type: "text" | "email" | "number" | "currency" | "date" | "status";
  required: boolean;
};

type Entity = {
  name: string;
  route: string;
  display_name: string;
  fields: Field[];
};

type Row = Record<string, string | number | null>;

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8080").replace(/\\/+$/, "");
const APP_TITLE =
'''
            + title_json
            + ''';
const ENTITIES: Entity[] =
'''
            + entities_json
            + ''';

export default function App() {
  const [activeRoute, setActiveRoute] = useState(ENTITIES[0]?.route ?? "");
  const activeEntity = useMemo(() => ENTITIES.find((entity) => entity.route === activeRoute) ?? ENTITIES[0], [activeRoute]);
  const [rows, setRows] = useState<Row[]>([]);
  const [form, setForm] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeEntity) return;
    const nextForm = Object.fromEntries(activeEntity.fields.map((field) => [field.name, defaultValue(field)]));
    setForm(nextForm);
    void loadRows(activeEntity.route);
  }, [activeEntity?.route]);

  async function loadRows(route = activeEntity.route) {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/${route}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setRows(await response.json());
    } catch {
      setError("No se pudo conectar con la API. Verifica que Docker Compose este ejecutandose.");
    } finally {
      setLoading(false);
    }
  }

  async function createRow() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/${activeEntity.route}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data: normalizeForm(activeEntity, form) }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setForm(Object.fromEntries(activeEntity.fields.map((field) => [field.name, defaultValue(field)])));
      await loadRows();
    } catch {
      setError("No se pudo crear el registro.");
    } finally {
      setLoading(false);
    }
  }

  async function deleteRow(id: string | number | null) {
    if (id === null) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/${activeEntity.route}/${id}`, { method: "DELETE" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await loadRows();
    } catch {
      setError("No se pudo eliminar el registro.");
    } finally {
      setLoading(false);
    }
  }

  const totalFields = ENTITIES.reduce((total, entity) => total + entity.fields.length, 0);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <span className="eyebrow">AI Cloud App Factory</span>
          <h1>{APP_TITLE}</h1>
          <p>Aplicacion CRUD cloud-native generada con React, FastAPI y PostgreSQL.</p>
        </div>
        <div className="status-row">
          <span><CheckCircle2 size={15} /> Local ready</span>
          <span><Database size={15} /> {ENTITIES.length} modulos</span>
          <span>{totalFields} campos</span>
        </div>
      </header>

      <nav className="module-tabs" aria-label="Modulos">
        {ENTITIES.map((entity) => (
          <button key={entity.route} className={entity.route === activeEntity.route ? "active" : ""} onClick={() => setActiveRoute(entity.route)}>
            {entity.display_name}
          </button>
        ))}
      </nav>

      <section className="workbench">
        <aside className="form-panel">
          <div className="panel-head">
            <h2>Nuevo registro</h2>
            <Plus size={18} />
          </div>
          {activeEntity.fields.map((field) => (
            <label key={field.name} className="field">
              <span>{field.label}</span>
              <input
                type={inputType(field)}
                value={form[field.name] ?? ""}
                onChange={(event) => setForm((current) => ({ ...current, [field.name]: event.target.value }))}
              />
            </label>
          ))}
          <button className="primary" onClick={() => void createRow()} disabled={loading}>
            {loading ? <Activity className="spin" size={16} /> : <Plus size={16} />}
            Crear
          </button>
          {error && <p className="error">{error}</p>}
        </aside>

        <section className="data-panel">
          <div className="panel-head">
            <div>
              <h2>{activeEntity.display_name}</h2>
              <span>{rows.length} registros</span>
            </div>
            <button className="icon-button" onClick={() => void loadRows()} aria-label="Actualizar">
              <RefreshCw size={16} />
            </button>
          </div>
          <div className="table">
            <div className="table-row table-head" style={{ gridTemplateColumns: gridColumns(activeEntity) }}>
              <span>ID</span>
              {activeEntity.fields.map((field) => <span key={field.name}>{field.label}</span>)}
              <span>Accion</span>
            </div>
            {rows.map((row) => (
              <div className="table-row" key={String(row.id)} style={{ gridTemplateColumns: gridColumns(activeEntity) }}>
                <span>{row.id}</span>
                {activeEntity.fields.map((field) => <span key={field.name}>{String(row[field.name] ?? "")}</span>)}
                <button className="delete-button" onClick={() => void deleteRow(row.id)}>
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            {!loading && rows.length === 0 && <div className="empty">Sin registros todavia.</div>}
          </div>
        </section>
      </section>
    </main>
  );
}

function inputType(field: Field) {
  if (field.type === "email") return "email";
  if (field.type === "number" || field.type === "currency") return "number";
  if (field.type === "date") return "date";
  return "text";
}

function defaultValue(field: Field) {
  if (field.type === "status") return "activo";
  if (field.type === "number" || field.type === "currency") return "0";
  return "";
}

function normalizeForm(entity: Entity, form: Record<string, string>) {
  return Object.fromEntries(entity.fields.map((field) => {
    const value = form[field.name] ?? "";
    if (field.type === "number") return [field.name, Number.parseInt(value || "0", 10)];
    if (field.type === "currency") return [field.name, Number.parseFloat(value || "0")];
    return [field.name, value];
  }));
}

function gridColumns(entity: Entity) {
  return `72px repeat(${entity.fields.length}, minmax(130px, 1fr)) 84px`;
}
'''
        )

    def _frontend_styles_template(self) -> str:
        return """
        :root {
          color: #17202a;
          background: #f4f7f9;
          font-family: Inter, ui-sans-serif, system-ui, sans-serif;
        }

        * {
          box-sizing: border-box;
        }

        body {
          margin: 0;
          min-width: 320px;
        }

        button,
        input {
          font: inherit;
        }

        .app-shell {
          display: grid;
          gap: 22px;
          min-height: 100vh;
          padding: 30px;
        }

        .topbar {
          align-items: flex-start;
          display: flex;
          gap: 20px;
          justify-content: space-between;
        }

        .eyebrow {
          color: #17636f;
          font-size: 0.76rem;
          font-weight: 900;
          text-transform: uppercase;
        }

        h1,
        h2,
        p {
          margin: 0;
        }

        h1 {
          font-size: clamp(2rem, 4vw, 3.4rem);
          line-height: 1.04;
          margin-top: 8px;
        }

        .topbar p {
          color: #526270;
          margin-top: 10px;
        }

        .status-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          justify-content: flex-end;
        }

        .status-row span {
          align-items: center;
          background: #ffffff;
          border: 1px solid #d9e2e8;
          border-radius: 999px;
          color: #405365;
          display: inline-flex;
          font-size: 0.82rem;
          font-weight: 800;
          gap: 6px;
          min-height: 32px;
          padding: 6px 10px;
        }

        .module-tabs {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .module-tabs button,
        .icon-button {
          background: #ffffff;
          border: 1px solid #d0dce6;
          border-radius: 7px;
          color: #405365;
          cursor: pointer;
          font-weight: 800;
          min-height: 38px;
          padding: 8px 12px;
        }

        .module-tabs button.active {
          background: #17636f;
          border-color: #17636f;
          color: #ffffff;
        }

        .workbench {
          display: grid;
          gap: 18px;
          grid-template-columns: 340px 1fr;
        }

        .form-panel,
        .data-panel {
          background: #ffffff;
          border: 1px solid #d9e2e8;
          border-radius: 8px;
          box-shadow: 0 16px 40px rgb(22 32 42 / 0.08);
          padding: 18px;
        }

        .form-panel {
          align-self: start;
          display: grid;
          gap: 14px;
        }

        .panel-head {
          align-items: center;
          display: flex;
          gap: 10px;
          justify-content: space-between;
        }

        .panel-head span {
          color: #637283;
          font-size: 0.84rem;
        }

        .field {
          display: grid;
          gap: 6px;
        }

        .field span {
          color: #526270;
          font-size: 0.82rem;
          font-weight: 800;
        }

        .field input {
          border: 1px solid #cbd9e2;
          border-radius: 7px;
          min-height: 42px;
          padding: 8px 10px;
        }

        .primary {
          align-items: center;
          background: #17636f;
          border: 1px solid #17636f;
          border-radius: 7px;
          color: #ffffff;
          cursor: pointer;
          display: inline-flex;
          font-weight: 900;
          gap: 8px;
          justify-content: center;
          min-height: 42px;
          padding: 9px 14px;
        }

        .primary:disabled {
          cursor: progress;
          opacity: 0.72;
        }

        .error {
          background: #fef2f2;
          border: 1px solid #fecaca;
          border-radius: 7px;
          color: #991b1b;
          padding: 10px;
        }

        .table {
          margin-top: 16px;
          overflow-x: auto;
        }

        .table-row {
          align-items: center;
          border-bottom: 1px solid #edf2f6;
          display: grid;
          gap: 10px;
          min-width: 720px;
          padding: 10px 0;
        }

        .table-head {
          color: #637283;
          font-size: 0.78rem;
          font-weight: 900;
          text-transform: uppercase;
        }

        .delete-button {
          align-items: center;
          background: #fff1f2;
          border: 1px solid #fecdd3;
          border-radius: 7px;
          color: #be123c;
          cursor: pointer;
          display: inline-flex;
          height: 32px;
          justify-content: center;
          width: 38px;
        }

        .empty {
          color: #637283;
          padding: 22px 0;
        }

        .spin {
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to {
            transform: rotate(360deg);
          }
        }

        @media (max-width: 900px) {
          .app-shell {
            padding: 18px;
          }

          .topbar,
          .workbench {
            grid-template-columns: 1fr;
          }

          .topbar {
            display: grid;
          }

          .status-row {
            justify-content: flex-start;
          }
        }
        """

    def _frontend_dockerfile_template(self) -> str:
        return """
        FROM node:20-alpine AS build
        WORKDIR /app
        ARG VITE_API_BASE_URL=http://localhost:8080
        ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
        COPY package.json ./
        RUN npm install
        COPY . .
        RUN npm run build

        FROM nginx:1.27-alpine
        COPY nginx.conf /etc/nginx/conf.d/default.conf
        COPY --from=build /app/dist /usr/share/nginx/html
        EXPOSE 80
        """

    def _frontend_nginx_template(self) -> str:
        return """
        server {
          listen 80;
          server_name _;
          root /usr/share/nginx/html;
          index index.html;

          location / {
            try_files $uri $uri/ /index.html;
          }
        }
        """

    def _github_workflow_template(self, plan: AppFactoryPlanResponse) -> str:
        existing_env = self._existing_container_app_environment()
        container_app_resource_group = existing_env["resourceGroup"] if existing_env else f"rg-{plan.slug}-dev"
        return f"""
        name: Deploy Azure Container Apps

        on:
          workflow_dispatch:
          push:
            branches: ["main"]

        env:
          RESOURCE_GROUP: rg-{plan.slug}-dev
          CONTAINER_APP_RESOURCE_GROUP: {container_app_resource_group}
          API_APP_NAME: ca-{plan.slug}-api
          WEB_APP_NAME: ca-{plan.slug}-web
          APP_SLUG: {plan.slug}

        jobs:
          deploy:
            runs-on: ubuntu-latest
            permissions:
              id-token: write
              contents: read

            steps:
              - uses: actions/checkout@v4

              - uses: azure/login@v2
                with:
                  client-id: ${{{{ secrets.AZURE_CLIENT_ID }}}}
                  tenant-id: ${{{{ secrets.AZURE_TENANT_ID }}}}
                  subscription-id: ${{{{ secrets.AZURE_SUBSCRIPTION_ID }}}}

              - name: Resolve generated ACR
                run: |
                  ACR_NAME=$(az acr list -g "$RESOURCE_GROUP" --query "[?tags.app=='{plan.slug}'].name | [0]" -o tsv)
                  if [ -z "$ACR_NAME" ]; then
                    echo "No ACR found in $RESOURCE_GROUP for app tag {plan.slug}" >&2
                    exit 1
                  fi
                  echo "ACR_NAME=$ACR_NAME" >> "$GITHUB_ENV"

              - name: Build and push API
                run: |
                  az acr build --registry "$ACR_NAME" --image api:${{{{ github.sha }}}} ./backend

              - name: Build and push Web
                run: |
                  API_FQDN=$(az containerapp show -g "$CONTAINER_APP_RESOURCE_GROUP" -n "$API_APP_NAME" --query properties.configuration.ingress.fqdn -o tsv)
                  az acr build --registry "$ACR_NAME" --image web:${{{{ github.sha }}}} ./frontend --build-arg VITE_API_BASE_URL="https://$API_FQDN"

              - name: Update API
                run: |
                  LOGIN_SERVER=$(az acr show -n "$ACR_NAME" --query loginServer -o tsv)
                  WEB_FQDN=$(az containerapp show -g "$CONTAINER_APP_RESOURCE_GROUP" -n "$WEB_APP_NAME" --query properties.configuration.ingress.fqdn -o tsv)
                  az containerapp update -g "$CONTAINER_APP_RESOURCE_GROUP" -n "$API_APP_NAME" \\
                    --image "$LOGIN_SERVER/api:${{{{ github.sha }}}}" \\
                    --set-env-vars APP_NAME="$APP_SLUG" FRONTEND_ORIGINS="https://$WEB_FQDN"

              - name: Update Web
                run: |
                  LOGIN_SERVER=$(az acr show -n "$ACR_NAME" --query loginServer -o tsv)
                  az containerapp update -g "$CONTAINER_APP_RESOURCE_GROUP" -n "$WEB_APP_NAME" --image "$LOGIN_SERVER/web:${{{{ github.sha }}}}"
        """

    def _terraform_versions_template(self) -> str:
        return """
        terraform {
          required_version = ">= 1.6.0"

          required_providers {
            azurerm = {
              source  = "hashicorp/azurerm"
              version = "~> 4.0"
            }
            random = {
              source  = "hashicorp/random"
              version = "~> 3.6"
            }
          }
        }

        provider "azurerm" {
          features {}
        }
        """

    def _terraform_main_template(self, plan: AppFactoryPlanResponse) -> str:
        compact = self._compact_slug(plan.slug)
        kv_compact = self._key_vault_slug(plan.slug)
        return f"""
        locals {{
          name = "{plan.slug}"
          use_existing_container_app_environment = trimspace(var.existing_container_app_environment_id) != ""
          container_app_environment_id           = local.use_existing_container_app_environment ? var.existing_container_app_environment_id : azurerm_container_app_environment.main[0].id
          container_app_resource_group_name      = trimspace(var.existing_container_app_resource_group_name) != "" ? var.existing_container_app_resource_group_name : azurerm_resource_group.main.name
          tags = {{
            app       = "{plan.slug}"
            generated = "ai-cloud-app-factory"
            env       = var.environment
          }}
        }}

        resource "random_string" "suffix" {{
          length  = 6
          upper   = false
          special = false
        }}

        resource "random_string" "postgres_suffix" {{
          length  = 6
          upper   = false
          special = false
        }}

        resource "azurerm_resource_group" "main" {{
          name     = "rg-${{local.name}}-${{var.environment}}"
          location = var.location
          tags     = local.tags
        }}

        resource "azurerm_log_analytics_workspace" "main" {{
          count               = local.use_existing_container_app_environment ? 0 : 1
          name                = "law-${{local.name}}-${{var.environment}}"
          location            = azurerm_resource_group.main.location
          resource_group_name = azurerm_resource_group.main.name
          sku                 = "PerGB2018"
          retention_in_days   = 30
          tags                = local.tags
        }}

        resource "azurerm_container_registry" "main" {{
          name                = "acr{compact}${{random_string.suffix.result}}"
          location            = azurerm_resource_group.main.location
          resource_group_name = azurerm_resource_group.main.name
          sku                 = "Basic"
          admin_enabled       = true
          tags                = local.tags
        }}

        resource "azurerm_postgresql_flexible_server" "main" {{
          name                   = "psql-${{local.name}}-${{random_string.postgres_suffix.result}}"
          resource_group_name    = azurerm_resource_group.main.name
          location               = var.postgres_location
          version                = "16"
          administrator_login    = var.postgres_admin_user
          administrator_password = var.postgres_admin_password
          sku_name               = "B_Standard_B1ms"
          storage_mb             = 32768
          backup_retention_days  = 7
          tags                   = local.tags
        }}

        resource "azurerm_postgresql_flexible_server_database" "app" {{
          name      = var.postgres_database
          server_id = azurerm_postgresql_flexible_server.main.id
          charset   = "UTF8"
          collation = "en_US.utf8"
        }}

        resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {{
          name             = "allow-azure-services"
          server_id        = azurerm_postgresql_flexible_server.main.id
          start_ip_address = "0.0.0.0"
          end_ip_address   = "0.0.0.0"
        }}

        resource "azurerm_key_vault" "main" {{
          name                       = "kv{kv_compact}${{random_string.suffix.result}}"
          location                   = azurerm_resource_group.main.location
          resource_group_name        = azurerm_resource_group.main.name
          tenant_id                  = data.azurerm_client_config.current.tenant_id
          sku_name                   = "standard"
          soft_delete_retention_days = 7
          tags                       = local.tags
        }}

        data "azurerm_client_config" "current" {{}}

        resource "azurerm_container_app_environment" "main" {{
          count                      = local.use_existing_container_app_environment ? 0 : 1
          name                       = "cae-${{local.name}}-${{var.environment}}"
          location                   = azurerm_resource_group.main.location
          resource_group_name        = azurerm_resource_group.main.name
          log_analytics_workspace_id = azurerm_log_analytics_workspace.main[0].id
          tags                       = local.tags
        }}

        resource "azurerm_container_app" "api" {{
          name                         = "ca-${{local.name}}-api"
          container_app_environment_id = local.container_app_environment_id
          resource_group_name          = local.container_app_resource_group_name
          revision_mode                = "Single"
          tags                         = local.tags

          secret {{
            name  = "acr-password"
            value = azurerm_container_registry.main.admin_password
          }}

          secret {{
            name  = "database-url"
            value = "postgresql+psycopg://${{var.postgres_admin_user}}:${{var.postgres_admin_password}}@${{azurerm_postgresql_flexible_server.main.fqdn}}:5432/${{azurerm_postgresql_flexible_server_database.app.name}}?sslmode=require"
          }}

          registry {{
            server               = azurerm_container_registry.main.login_server
            username             = azurerm_container_registry.main.admin_username
            password_secret_name = "acr-password"
          }}

          ingress {{
            external_enabled = true
            target_port      = 8000
            traffic_weight {{
              percentage      = 100
              latest_revision = true
            }}
          }}

          template {{
            min_replicas = 1
            max_replicas = 2

            container {{
              name   = "api"
              image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
              cpu    = 0.5
              memory = "1Gi"

              env {{
                name        = "DATABASE_URL"
                secret_name = "database-url"
              }}

              env {{
                name  = "APP_NAME"
                value = local.name
              }}

              env {{
                name  = "FRONTEND_ORIGINS"
                value = "https://${{azurerm_container_app.web.ingress[0].fqdn}}"
              }}
            }}
          }}

          lifecycle {{
            ignore_changes = [template[0].container[0].image]
          }}
        }}

        resource "azurerm_container_app" "web" {{
          name                         = "ca-${{local.name}}-web"
          container_app_environment_id = local.container_app_environment_id
          resource_group_name          = local.container_app_resource_group_name
          revision_mode                = "Single"
          tags                         = local.tags

          secret {{
            name  = "acr-password"
            value = azurerm_container_registry.main.admin_password
          }}

          registry {{
            server               = azurerm_container_registry.main.login_server
            username             = azurerm_container_registry.main.admin_username
            password_secret_name = "acr-password"
          }}

          ingress {{
            external_enabled = true
            target_port      = 80
            traffic_weight {{
              percentage      = 100
              latest_revision = true
            }}
          }}

          template {{
            min_replicas = 1
            max_replicas = 2

            container {{
              name   = "web"
              image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
              cpu    = 0.25
              memory = "0.5Gi"
            }}
          }}

          lifecycle {{
            ignore_changes = [template[0].container[0].image]
          }}
        }}
        """

    def _terraform_variables_template(self) -> str:
        return """
        variable "location" {
          type        = string
          description = "Azure region for Resource Group, ACR, Key Vault and new Container Apps Environment."
          default     = "eastus"
        }

        variable "postgres_location" {
          type        = string
          description = "Azure region for PostgreSQL Flexible Server. Azure for Students may restrict eastus."
          default     = "mexicocentral"
        }

        variable "environment" {
          type        = string
          description = "Environment name."
          default     = "dev"
        }

        variable "existing_container_app_environment_id" {
          type        = string
          description = "Existing Container Apps Environment ID. Set this to reuse the single allowed environment in constrained subscriptions."
          default     = ""
        }

        variable "existing_container_app_resource_group_name" {
          type        = string
          description = "Resource group where Container Apps should be created when using an existing environment."
          default     = ""
        }

        variable "postgres_admin_user" {
          type        = string
          description = "PostgreSQL admin user."
          default     = "appadmin"
        }

        variable "postgres_admin_password" {
          type        = string
          description = "PostgreSQL admin password."
          sensitive   = true
        }

        variable "postgres_database" {
          type        = string
          description = "Application database name."
          default     = "appdb"
        }
        """

    def _terraform_outputs_template(self) -> str:
        return """
        output "resource_group_name" {
          value = azurerm_resource_group.main.name
        }

        output "container_registry_login_server" {
          value = azurerm_container_registry.main.login_server
        }

        output "api_url" {
          value = "https://${azurerm_container_app.api.ingress[0].fqdn}"
        }

        output "web_url" {
          value = "https://${azurerm_container_app.web.ingress[0].fqdn}"
        }

        output "api_docs_url" {
          value = "https://${azurerm_container_app.api.ingress[0].fqdn}/docs"
        }

        output "container_app_environment_id" {
          value = local.container_app_environment_id
        }
        """

    def _terraform_tfvars_template(self, plan: AppFactoryPlanResponse) -> str:
        existing_env = self._existing_container_app_environment()
        existing_env_id = existing_env["id"] if existing_env else ""
        existing_env_rg = existing_env["resourceGroup"] if existing_env else ""
        return f"""location                                   = "eastus"
postgres_location                          = "mexicocentral"
environment                                = "dev"
existing_container_app_environment_id      = "{existing_env_id}"
existing_container_app_resource_group_name = "{existing_env_rg}"
postgres_admin_user                        = "appadmin"
postgres_admin_password                    = "ChangeThisPassword123!"
postgres_database                          = "{self._compact_slug(plan.slug)}db"
"""

    def _architecture_doc_template(self, plan: AppFactoryPlanResponse) -> str:
        resources = "\n".join(f"- {resource.type}: `{resource.name}`" for resource in plan.resources)
        return f"""
        # Arquitectura

        `{plan.project_name}` se compone de:

        - React + Vite para la experiencia web.
        - FastAPI para API REST y documentacion OpenAPI.
        - PostgreSQL para persistencia.
        - Docker Compose para ejecucion local.
        - Azure Container Apps para ejecucion cloud.
        - Azure Container Registry para imagenes.
        - Key Vault para secretos.
        - Log Analytics para telemetria base.

        ## Recursos Azure propuestos

        {resources}
        """

    def _azure_doc_template(self, plan: AppFactoryPlanResponse) -> str:
        return f"""
        # Despliegue Azure

        ## Pre-requisitos

        - Azure CLI autenticado.
        - Terraform instalado.
        - Permisos para crear Resource Groups, ACR, Container Apps, PostgreSQL y Key Vault.
        - GitHub Actions con OIDC o service principal.

        ## Pasos

        Despliegue completo desde esta maquina:

        ```powershell
        .\\scripts\\deploy-azure.ps1
        ```

        Infraestructura solamente:

        ```powershell
        cd infra/terraform
        copy terraform.tfvars.example terraform.tfvars
        terraform init
        terraform plan
        terraform apply -auto-approve
        ```

        Cuando Terraform entregue `api_url` y `web_url`, configura estos secretos en GitHub:

        - `AZURE_CLIENT_ID`
        - `AZURE_TENANT_ID`
        - `AZURE_SUBSCRIPTION_ID`

        Despues ejecuta el workflow `Deploy Azure Container Apps`.

        ## App

        Nombre: `{plan.project_name}`
        Slug: `{plan.slug}`
        """

    def _healthcheck_script_template(self) -> str:
        return """
        $ErrorActionPreference = "Stop"
        Invoke-RestMethod http://localhost:8080/health
        Invoke-RestMethod http://localhost:8080/api/schema
        Write-Host "Local API is healthy."
        """

    def _azure_deploy_script_template(self, plan: AppFactoryPlanResponse) -> str:
        existing_env = self._existing_container_app_environment()
        container_app_resource_group = existing_env["resourceGroup"] if existing_env else f"rg-{plan.slug}-dev"
        return f"""
        $ErrorActionPreference = "Stop"

        $ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
        $TerraformDir = Join-Path $ProjectRoot "infra\\terraform"
        $ResourceGroup = "rg-{plan.slug}-dev"
        $ContainerAppResourceGroup = "{container_app_resource_group}"
        $ApiAppName = "ca-{plan.slug}-api"
        $WebAppName = "ca-{plan.slug}-web"
        $AppSlug = "{plan.slug}"

        Push-Location $TerraformDir
        try {{
            if (-not (Test-Path "terraform.tfvars") -and (Test-Path "terraform.tfvars.example")) {{
                Copy-Item "terraform.tfvars.example" "terraform.tfvars"
            }}
            terraform init
            terraform apply -auto-approve
            $ApiUrl = terraform output -raw api_url
            $WebUrl = terraform output -raw web_url
            $AcrLoginServer = terraform output -raw container_registry_login_server
        }}
        finally {{
            Pop-Location
        }}

        $AcrName = ($AcrLoginServer -split "\\.")[0]
        $ImageTag = "manual-$(Get-Date -Format yyyyMMddHHmmss)"

        az acr login --name $AcrName

        docker build -t "$AcrLoginServer/api:$ImageTag" (Join-Path $ProjectRoot "backend")
        docker push "$AcrLoginServer/api:$ImageTag"

        docker build --build-arg "VITE_API_BASE_URL=$ApiUrl" -t "$AcrLoginServer/web:$ImageTag" (Join-Path $ProjectRoot "frontend")
        docker push "$AcrLoginServer/web:$ImageTag"

        az containerapp update `
            --resource-group $ContainerAppResourceGroup `
            --name $ApiAppName `
            --image "$AcrLoginServer/api:$ImageTag" `
            --set-env-vars "APP_NAME=$AppSlug" "FRONTEND_ORIGINS=$WebUrl"

        az containerapp update `
            --resource-group $ContainerAppResourceGroup `
            --name $WebAppName `
            --image "$AcrLoginServer/web:$ImageTag"

        Write-Host "Frontend: $WebUrl"
        Write-Host "API: $ApiUrl"
        Write-Host "API Docs: $ApiUrl/docs"
        """

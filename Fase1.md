# Plan De Ejecución Fase 1: Plataforma Base

## Resumen

Objetivo de la fase 1: dejar funcionando una plataforma cloud real con frontend, backend, base de datos, secretos, contenedores y CI/CD, lista para que en fase 2 se agregue Query Governance y DBA Copilot.

Entregable principal: portal web desplegado en Azure, conectado a una API FastAPI en Azure Container Apps, usando PostgreSQL como base operacional y Key Vault para secretos.

## Implementación Base

- Crear estructura inicial del proyecto:
  - `/frontend`: React + Vite + Tailwind.
  - `/backend`: FastAPI + SQLAlchemy + Alembic.
  - `/infra`: Terraform o Bicep para Azure.
  - `/docs`: arquitectura, demo técnica y decisiones.
  - `.github/workflows`: pipelines CI/CD.

- Implementar frontend mínimo:
  - Dashboard principal de la plataforma.
  - Vista de estado de servicios.
  - Vista de ambientes `DEV`, `QA`, `PROD`.
  - Indicadores mock iniciales: apps desplegadas, estado API, base conectada, últimos despliegues.
  - Configurar variables de entorno para consumir el backend.

- Implementar backend base:
  - FastAPI con endpoints:
    - `GET /health`
    - `GET /api/platform/status`
    - `GET /api/environments`
    - `GET /api/services`
    - `GET /api/deployments`
  - Configuración por variables de entorno.
  - Conexión real a PostgreSQL.
  - Logging estructurado básico.
  - CORS configurado para el frontend.
  - Manejo estándar de errores.

- Implementar base PostgreSQL:
  - Tablas iniciales:
    - `environments`
    - `services`
    - `deployments`
    - `audit_events`
    - `platform_settings`
  - Datos semilla para demo.
  - Migraciones con Alembic.
  - Usuario de aplicación con permisos mínimos.

## Azure E Infraestructura

- Crear recursos Azure de fase 1:
  - Resource Group.
  - Azure Static Web Apps para frontend.
  - Azure Container Apps para backend.
  - Azure Container Registry para imagen Docker.
  - Azure Database for PostgreSQL Flexible Server.
  - Azure Key Vault.
  - Log Analytics Workspace.
  - Azure Monitor básico.
  - Budget bajo, recomendado entre USD 10 y USD 20.

- Configurar secretos:
  - `DATABASE_URL`
  - credenciales PostgreSQL
  - configuración de entorno
  - futuros placeholders para Gemini, Databricks y DataHub, sin activarlos aún.
  - El backend debe leer secretos desde variables inyectadas por Container Apps, no hardcodeadas.

- Contenerizar backend:
  - Crear `Dockerfile`.
  - Crear imagen FastAPI productiva.
  - Exponer puerto correcto.
  - Health check compatible con Azure Container Apps.

- Configurar CI/CD con GitHub Actions:
  - Workflow frontend:
    - instalar dependencias
    - build
    - deploy a Azure Static Web Apps
  - Workflow backend:
    - instalar dependencias
    - ejecutar pruebas
    - construir imagen Docker
    - publicar en ACR
    - desplegar en Azure Container Apps
  - No incluir secretos en el repositorio.

## Criterios Para Pasar A Fase 2

- El frontend abre desde una URL pública de Azure.
- El backend responde correctamente en `/health`.
- El frontend consume al menos un endpoint real del backend.
- El backend conecta correctamente a PostgreSQL.
- Las migraciones crean las tablas base.
- Existe auditoría mínima en `audit_events`.
- Los secretos están fuera del código y gestionados desde Azure.
- El deploy del backend se puede ejecutar desde GitHub Actions.
- El deploy del frontend se puede ejecutar desde GitHub Actions.
- Azure Monitor o Log Analytics recibe logs básicos del backend.
- Existe documentación mínima de:
  - arquitectura fase 1
  - variables de entorno
  - despliegue
  - costos
  - cómo apagar recursos para ahorrar

## Test Plan

- Backend:
  - Probar `GET /health`.
  - Probar conexión a DB.
  - Probar endpoints de plataforma.
  - Probar creación de evento de auditoría.
  - Probar error si falta configuración crítica.

- Frontend:
  - Verificar carga del dashboard.
  - Verificar conexión con backend.
  - Verificar estados de loading, error y datos disponibles.
  - Verificar layout responsive básico.

- Infraestructura:
  - Validar que el backend desplegado usa variables/secretos de Azure.
  - Validar que Container Apps expone la API.
  - Validar que Static Web Apps apunta al backend correcto.
  - Validar logs en Azure Monitor.
  - Validar que no haya secretos en Git.

## Orden De Trabajo Recomendado

1. Crear estructura del monorepo.
2. Implementar backend FastAPI local con `/health`.
3. Agregar PostgreSQL local o cloud y migraciones.
4. Crear modelos base: ambientes, servicios, despliegues y auditoría.
5. Implementar frontend React con dashboard inicial.
6. Conectar frontend con backend local.
7. Crear Dockerfile del backend.
8. Crear infraestructura Azure.
9. Desplegar PostgreSQL, Key Vault, ACR y Container Apps.
10. Desplegar frontend en Azure Static Web Apps.
11. Configurar GitHub Actions.
12. Verificar logs, costos y documentación.
13. Hacer demo de fase 1.
14. Congelar fase 1 antes de iniciar Query Governance.

## Asunciones

- Para fase 1 se usará PostgreSQL como base principal.
- DataHub, Databricks, Gemini y Purview no se implementan todavía; solo se preparan variables/placeholders.
- El frontend mostrará datos reales desde la API, aunque algunos valores de negocio todavía sean semilla o mock controlado.
- La prioridad de fase 1 es plataforma desplegable y estable, no funcionalidades avanzadas de gobierno de datos.
- Se recomienda Terraform o Bicep, pero elegir uno solo para evitar duplicar infraestructura.

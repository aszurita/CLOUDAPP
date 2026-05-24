# Explicacion De La Carpeta Infra

La carpeta `infra/` contiene la infraestructura como codigo del proyecto. En este caso usa Terraform para crear en Azure los recursos necesarios de la fase 1 sin tener que configurarlos manualmente desde el portal.

## Que Hace En Este Proyecto

Cuando ejecutas Terraform desde `infra/terraform`, el proyecto intenta crear una plataforma base en Azure para que el portal y el backend puedan correr en la nube.

El flujo general es:

```text
Terraform
  crea recursos en Azure
    para desplegar frontend, backend, base de datos, secretos, logs y presupuesto
```

Los comandos principales son:

```bash
terraform init
terraform plan
terraform apply
```

`terraform init` prepara Terraform y descarga los proveedores necesarios.

`terraform plan` muestra lo que Terraform va a crear, cambiar o eliminar.

`terraform apply` crea o modifica los recursos reales en Azure.

## Recursos Que Crea

### 1. Resource Group

Crea un grupo de recursos llamado parecido a:

```text
rg-cloudapp-dev
```

Sirve como una carpeta dentro de Azure donde quedan agrupadas todas las piezas del proyecto.

Funcion: mantener ordenados los recursos y poder administrarlos juntos.

### 2. Log Analytics Workspace

Crea un espacio para recibir logs y telemetria del backend.

Sirve para ver informacion tecnica como:

```text
errores
arranques de la aplicacion
eventos del contenedor
logs del backend
```

Funcion: dar visibilidad operativa. Si algo falla, aqui se puede investigar.

### 3. Azure Container Registry

Crea un registro privado de imagenes Docker.

El backend FastAPI se empaqueta como una imagen Docker. Esa imagen se sube al Container Registry y luego Azure Container Apps la usa para ejecutar la API.

Funcion: guardar versiones desplegables del backend.

### 4. Key Vault

Crea una boveda de secretos.

Guarda valores sensibles como:

```text
DATABASE_URL
OPENAI_API_KEY
DATABRICKS_HOST
DATAHUB_SERVER
```

En fase 1, OpenAI, Databricks y DataHub se preparan como integraciones. En fase 2 se activa OpenAI para Query Governance y DBA Copilot; Databricks y DataHub quedan para fases posteriores.

Funcion: evitar que claves, passwords o URLs sensibles queden escritas directamente en el codigo.

### 5. PostgreSQL Flexible Server

Crea una base de datos PostgreSQL administrada por Azure.

El backend la usa para guardar:

```text
environments
services
deployments
audit_events
platform_settings
```

Funcion: ser la base operacional de la plataforma.

Nota: PostgreSQL puede estar restringido por region segun el tipo de suscripcion. Por eso la infraestructura usa una variable separada llamada `postgres_location`. En este proyecto se usa `mexicocentral` para PostgreSQL porque tu Azure for Students permite esa region y PostgreSQL Flexible Server reporta disponibilidad ahi.

Si un intento fallido deja reservado el nombre del servidor, se puede cambiar solo el sufijo con `postgres_server_name_suffix`. Esto permite crear un PostgreSQL nuevo sin renombrar el resto de recursos ya creados.

### 6. PostgreSQL Database

Dentro del servidor PostgreSQL, crea una base llamada:

```text
cloudapp
```

Funcion: guardar los datos especificos de esta aplicacion.

### 7. Firewall Rules De PostgreSQL

Crea reglas de acceso para la base de datos.

Hay una regla para permitir servicios de Azure y otra opcional para permitir tu IP publica si defines `allowed_client_ip`.

Funcion: controlar quien puede conectarse a la base.

### 8. Container Apps Environment

Crea el ambiente donde se ejecutara el backend en contenedores.

Funcion: ser el entorno administrado donde vive la API FastAPI.

### 9. Azure Container App

Crea la aplicacion contenedorizada del backend.

En fase inicial usa una imagen placeholder:

```text
mcr.microsoft.com/azuredocs/containerapps-helloworld:latest
```

Luego el workflow de GitHub Actions reemplaza esa imagen por la imagen real del backend FastAPI.

Funcion: ejecutar el backend en la nube sin administrar servidores manualmente.

### 10. Static Web App

Crea el recurso para publicar el frontend React.

Funcion: servir el portal web desde una URL publica de Azure.

Nota: Azure Static Web Apps no esta disponible en todas las regiones. Por eso la infraestructura usa `static_web_app_location`, con `eastus2` como valor recomendado.

### 11. Budget

Crea un presupuesto mensual para el Resource Group.

Por defecto esta en:

```text
20 USD
```

Si agregas correos en `budget_contact_emails`, Azure puede enviar notificaciones cuando se llegue al 80% del presupuesto.

Funcion: reducir el riesgo de gastar de mas.

Nota: Azure exige al menos un contacto para las notificaciones del presupuesto. Si `budget_contact_emails` esta vacio, Terraform no crea el presupuesto para evitar un error en `terraform apply`.

## Variables Importantes

El archivo `variables.tf` define valores configurables.

Las mas importantes son:

```text
project_name          nombre corto del proyecto
environment           ambiente, por ejemplo dev
location              region de Azure
postgres_location     region especifica para PostgreSQL
postgres_server_name_suffix sufijo opcional para el nombre de PostgreSQL
static_web_app_location region especifica para Static Web Apps
postgres_admin_user   usuario administrador de PostgreSQL
allowed_client_ip     IP permitida para conectarte a PostgreSQL
budget_amount_usd     presupuesto mensual
frontend_origin       URL permitida para que el frontend llame al backend
```

El archivo `terraform.tfvars.example` sirve como plantilla. Lo normal es copiarlo:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Y editar `terraform.tfvars` con tus valores reales.

## Outputs

El archivo `outputs.tf` muestra valores utiles despues del despliegue, por ejemplo:

```text
resource_group_name
acr_login_server
container_app_name
container_app_url
static_web_app_name
static_web_app_default_host_name
key_vault_name
postgres_server_fqdn
```

Estos valores sirven para configurar GitHub Actions, revisar recursos en Azure o conectar el frontend con el backend.

Nota: la URL correcta para que el frontend llame al backend es la URL estable del Container App, no una URL de revision con doble guion. En este proyecto se ve asi:

```text
https://ca-cloudapp-dev-api.delightfulsea-04be8a68.eastus.azurecontainerapps.io
```

## Como Encaja Con El Proyecto

La aplicacion tiene dos piezas principales:

```text
frontend React
backend FastAPI
```

La infraestructura crea el lugar donde esas piezas van a vivir.

El mapa seria:

```text
React frontend
  -> Azure Static Web Apps

FastAPI backend
  -> Azure Container Apps

Docker image del backend
  -> Azure Container Registry

Datos de la plataforma
  -> Azure PostgreSQL

Secretos
  -> Azure Key Vault

Logs
  -> Log Analytics

Control de gasto
  -> Azure Budget
```

## Que No Hace Todavia

En fase 1, `infra/` no crea todavia:

```text
Databricks workspace real
DataHub real
Microsoft Purview
pipelines Bronze/Silver/Gold
servicios avanzados de IA
```

Solo deja placeholders para que esas fases sean mas faciles de conectar despues.

## Explicacion Para Alguien Que No Es De Computacion

Imagina que vas a abrir una oficina.

Antes de que las personas puedan trabajar, necesitas preparar varias cosas:

```text
un local
una caja fuerte
una bodega
una computadora central
un registro de actividad
un control de presupuesto
una recepcion para atender usuarios
```

La carpeta `infra/` es el plano que dice como construir esa oficina en Azure.

En esta analogia:

```text
Resource Group = la carpeta o edificio donde esta todo
Static Web App = la recepcion donde entra el usuario
Container App = la oficina donde trabaja el backend
PostgreSQL = el archivador donde se guardan los datos
Key Vault = la caja fuerte de claves y contrasenas
Container Registry = la bodega donde se guardan paquetes listos para usar
Log Analytics = el libro de novedades y errores
Budget = el limite de gasto mensual
```

Sin `infra/`, tendrias que entrar a Azure y crear todo a mano, boton por boton.

Con `infra/`, escribes el plano una vez y Terraform crea la oficina completa de forma ordenada.

La ventaja es que si manana necesitas repetir el proyecto, moverlo a otro ambiente o reconstruirlo, no dependes de memoria ni de capturas de pantalla. Tienes el plano exacto en codigo.

## Explicacion Corta Para Presentar

Puedes decirlo asi:

```text
La carpeta infra contiene la definicion automatizada de la nube del proyecto.
Con Terraform creo los recursos base de Azure: frontend, backend, base de datos, secretos, monitoreo, registro de contenedores y presupuesto.
Esto evita configuraciones manuales, permite versionar la infraestructura y hace que el despliegue sea repetible.
```

Y en lenguaje menos tecnico:

```text
Es el plano que construye automaticamente en Azure todo lo que la aplicacion necesita para funcionar.
```

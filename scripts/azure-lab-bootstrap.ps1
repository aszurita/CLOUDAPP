[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Password,

  [string]$HostName = "psql-cloudapp-dev-zgc5ku4.postgres.database.azure.com",
  [int]$Port = 5432,
  [string]$AdminUser = "cloudappadmin",
  [string]$LabDatabase = "lab",
  [string]$SqlFile = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($SqlFile)) {
  $SqlFile = Join-Path $PSScriptRoot "..\..\IA_BASES\lab\postgres\init.sql"
}

$resolvedSql = Resolve-Path -LiteralPath $SqlFile
$mountDir = Split-Path -Parent $resolvedSql.Path
$sqlName = Split-Path -Leaf $resolvedSql.Path
$envArg = "PGPASSWORD=$Password"
$adminConn = "host=$HostName port=$Port dbname=postgres user=$AdminUser sslmode=require"
$labConn = "host=$HostName port=$Port dbname=$LabDatabase user=$AdminUser sslmode=require"

Write-Host "Checking database '$LabDatabase' on $HostName..."
$exists = & docker run --rm -e $envArg postgres:16-alpine `
  psql $adminConn -tAc "SELECT 1 FROM pg_database WHERE datname = '$LabDatabase';"
if ($LASTEXITCODE -ne 0) {
  throw "Could not check database existence."
}

if (($exists | Out-String).Trim() -ne "1") {
  Write-Host "Creating database '$LabDatabase'..."
  & docker run --rm -e $envArg postgres:16-alpine `
    psql $adminConn -c "CREATE DATABASE ""$LabDatabase"";"
  if ($LASTEXITCODE -ne 0) {
    throw "Could not create database '$LabDatabase'."
  }
}

Write-Host "Loading schema/data from $resolvedSql..."
& docker run --rm -e $envArg -v "${mountDir}:/sql:ro" postgres:16-alpine `
  psql $labConn -f "/sql/$sqlName"
if ($LASTEXITCODE -ne 0) {
  throw "Lab SQL load finished with errors. Review PostgreSQL output above."
}

Write-Host "Lab bootstrap completed."

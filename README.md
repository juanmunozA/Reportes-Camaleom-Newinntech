# Camaleom New Inntech

Copia del automatizador Camaleom + Azure DevOps.

## Comandos rapidos

```powershell
npm start
```

Ejecuta el agente una vez, descarga Camaleom, consulta Azure con PAT y genera Excel + HTML.

```powershell
npm run loop
```

Deja el agente encendido en ciclo.

```powershell
npm run report
```

Ejecuta directamente el reporte una vez, sin el wrapper de agente.

```powershell
npm run azure
```

Consulta solo Azure.

## Pasar argumentos extra

```powershell
npm start -- --fecha-inicio 2026-06-30 --fecha-fin 2026-07-06 --sprint 278
```

```powershell
npm run report -- --camaleom-excel ".\camaleom_azure_reporte_app\descargas_reportes\ActividadesMisActividades.xlsx"
```

Los reportes salen en:

```text
camaleom_azure_reporte_app\salidas_reportes
```

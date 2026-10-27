# Registra (o actualiza) una tarea diaria en el Programador de tareas de Windows
# que ejecuta descargar_historico.py (todos los productos y mercados, últimos
# 30 días, fusionando con el histórico) desde la carpeta donde está este archivo.
# Si mueves la carpeta, vuelve a ejecutar este script.
param(
    [string]$Hora = "12:00",
    [int]$Dias = 30
)

$carpeta = Split-Path -Parent $MyInvocation.MyCommand.Path
$script  = Join-Path $carpeta "descargar_historico.py"
$python  = (Get-Command python -ErrorAction Stop).Source
$nombre  = "MAG - Precios agropecuarios"
$anterior = "MAG - Precio Papa Super Chola"

# La tarea anterior (solo papa) queda reemplazada por esta.
if (Get-ScheduledTask -TaskName $anterior -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $anterior -Confirm:$false
    Write-Output "Tarea anterior '$anterior' eliminada"
}

$accion   = New-ScheduledTaskAction -Execute $python -Argument "`"$script`" --dias $Dias" -WorkingDirectory $carpeta
$disparo  = New-ScheduledTaskTrigger -Daily -At $Hora
# StartWhenAvailable: si la PC estaba apagada a la hora indicada, corre al encenderla.
$opciones = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -RunOnlyIfNetworkAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $disparo -Settings $opciones `
    -Description "Descarga diaria de precios de todos los productos y mercados desde el SIPA/MAG" -Force | Out-Null

Write-Output "Tarea '$nombre' programada todos los dias a las $Hora (ultimos $Dias dias)"
Write-Output "Script: $script"

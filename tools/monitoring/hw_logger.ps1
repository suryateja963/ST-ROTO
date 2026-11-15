# ST-ROTO hardware logger: diagnose sudden power-offs on the development laptop.
# Appends one CSV line every $IntervalSec seconds to logs\hardware\hw_<date>.csv.
# Each line is written with open/append/close so a power loss loses at most one interval.
# Read-only telemetry; changes no settings. Stop it with:  Get-Process powershell | ? CommandLine -match hw_logger | Stop-Process
param([int]$IntervalSec = 5)

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$dir  = Join-Path $root "logs\hardware"
New-Item -ItemType Directory -Force $dir | Out-Null
$header = "time,gpu_temp_c,gpu_power_w,gpu_sm_mhz,gpu_util_pct,gpu_mem_mib,gpu_clock_event_reasons,gpu_pstate,cpu_util_pct,cpu_pct_max_freq,on_ac,battery_pct"
$counters = '\Processor Information(_Total)\% Processor Utility', '\Processor Information(_Total)\% of Maximum Frequency'

while ($true) {
    $file = Join-Path $dir ("hw_{0}.csv" -f (Get-Date -Format yyyyMMdd))
    if (-not (Test-Path $file)) { Add-Content -Path $file -Value $header -Encoding utf8 }
    try {
        $g = (nvidia-smi --query-gpu=temperature.gpu,power.draw,clocks.sm,utilization.gpu,memory.used,clocks_event_reasons.active,pstate --format=csv,noheader,nounits 2>$null) -replace '\s', ''
    } catch { $g = ",,,,,," }
    if (-not $g) { $g = ",,,,,," }
    try {
        $c = (Get-Counter $counters -ErrorAction Stop).CounterSamples
        $inv = [Globalization.CultureInfo]::InvariantCulture
        $cpu = $c[0].CookedValue.ToString("F1", $inv) + "," + $c[1].CookedValue.ToString("F0", $inv)
    } catch { $cpu = "," }
    try {
        $b = Get-CimInstance Win32_Battery -ErrorAction Stop | Select-Object -First 1
        $pwr = "{0},{1}" -f ([int]($b.BatteryStatus -eq 2)), $b.EstimatedChargeRemaining
    } catch { $pwr = "," }
    $line = "{0},{1},{2},{3}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $g, $cpu, $pwr
    Add-Content -Path $file -Value $line -Encoding utf8
    Start-Sleep -Seconds $IntervalSec
}

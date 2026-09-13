$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ws = "C:\Users\ysy\AppData\Roaming\reasonix\global-workspace\ar-risk-platform"
$utf8 = New-Object System.Text.UTF8Encoding($false)
function J($p) { ConvertFrom-Json ([IO.File]::ReadAllText($p, $utf8)) }
$mm = J (Join-Path $ws "data\machine_metrics.json")
$demo = J (Join-Path $ws "data\demo\demo_company.json")
$fin = $demo.finance
$has = @{}
foreach ($k in ($fin.Y0.PSObject.Properties.Name)) { $has[$k] = $true }
foreach ($k in ($fin.quarter.PSObject.Properties.Name)) { $has["q." + $k] = $true }
foreach ($k in ($fin.extra.PSObject.Properties.Name)) { $has["extra." + $k] = $true }
# note: metrics access quarters via top-level 'q.' prefix (y0 = annual Y0 dict only)
Write-Output "metric formulas/conds referenced keys (y0./y1./y2./q./extra.) vs demo finance keys:"
$missing = @()
foreach ($m in $mm.metrics) {
    foreach ($f in @($m.formula, ($m.rules | ForEach-Object { $_.cond }))) {
        if (-not $f) { continue }
        foreach ($mm2 in [regex]::Matches($f, '(?:y[012]\.|q\.|extra\.)([A-Za-z_]+)')) {
            $scope = $mm2.Value.Substring(0, $mm2.Value.IndexOf('.'))
            $key = $mm2.Groups[1].Value
            if ($scope -eq 'q') { $scope = 'quarter' }
            if ($scope -eq 'extra') { $scope = 'extra' }
            if (-not $fin.$scope.PSObject.Properties.Name -contains $key) { $missing += ("{0} [{1}] -> {2}.{3}" -f $m.id, $m.name, $scope, $key) }
        }
    }
}
if ($missing.Count) { Write-Output ($missing | Sort-Object -Unique) } else { Write-Output "ALL REFERENCED KEYS EXIST IN DEMO FINANCE" }

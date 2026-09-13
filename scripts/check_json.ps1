$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ws = "C:\Users\ysy\AppData\Roaming\reasonix\global-workspace\ar-risk-platform"
$utf8 = New-Object System.Text.UTF8Encoding($false)
Get-ChildItem -Path $ws -Recurse -Include *.json | ForEach-Object {
    try {
        $null = ConvertFrom-Json ([IO.File]::ReadAllText($_.FullName, $utf8))
        Write-Output ("OK   {0}" -f $_.FullName.Replace($ws, ''))
    } catch {
        Write-Output ("FAIL {0}: {1}" -f $_.FullName.Replace($ws, ''), $_.Exception.Message)
    }
}

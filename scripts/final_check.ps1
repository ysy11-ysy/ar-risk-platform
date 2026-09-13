$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ws = "C:\Users\ysy\AppData\Roaming\reasonix\global-workspace\ar-risk-platform"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$bad = 0
Get-ChildItem -Path $ws -Recurse -Filter *.py | ForEach-Object {
    $t = [IO.File]::ReadAllText($_.FullName, $utf8)
    foreach ($p in @('()', '{}', '[]')) {
        $o = ([regex]::Matches($t, [regex]::Escape($p.Substring(0, 1)))).Count
        $c = ([regex]::Matches($t, [regex]::Escape($p.Substring(1, 1)))).Count
        if ($o -ne $c) { $bad++; Write-Output ("UNBALANCED {0} {1}:{2}/{3}" -f $_.Name, $p, $o, $c) }
    }
}
Write-Output "py bracket check done, issues=$bad"
Get-ChildItem -Path $ws -Recurse -File | Where-Object { $_.FullName -notmatch 'sample-inputs' } | ForEach-Object {
    "{0,10:N1} KB  {1}" -f ($_.Length / 1KB), $_.FullName.Replace($ws + '\', '')
} | Sort-Object

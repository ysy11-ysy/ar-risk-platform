# build_rules.ps1  (ASCII-only source; Chinese text only from UTF-8 resource files)
# Parse the risk-rule workbook (data/raw/rules.xlsx) into structured JSON: data/rules.json
#
# Three layout families handled automatically:
#   F1 row-paired wide tables (R001-R004): indicator rows paired with per-indicator
#      threshold rows (same column, later rows); labels sparse in col A.
#   F2 inline compact tables (R005-R017 most): per signal column, one merged cell of
#      numbered formulas on/near the formula label row; one merged threshold cell.
#   F3 tier matrices (R005,R006,R007,R017): threshold area = 3 rows (tier words)
#      whose words sit in col B while descriptions start one column to the right
#      (author shifted the matrix right by one column; the last signal then has no
#      tier text and is left empty intentionally).
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.IO.Compression.FileSystem

$ws   = Split-Path -Parent $PSScriptRoot
$xlsx = Join-Path $ws "data\raw\rules.xlsx"
$lblF = Join-Path $ws "data\raw\labels.json"
$out  = Join-Path $ws "data\rules.json"
if (-not (Test-Path $xlsx)) { throw "missing rules workbook: $xlsx" }
$utf8 = New-Object System.Text.UTF8Encoding($false)
$labels = (ConvertFrom-Json ([IO.File]::ReadAllText($lblF, $utf8)))

function Get-ZipText($zipPath, $entryPath) {
    $zip = [IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $e = $zip.Entries | Where-Object FullName -eq $entryPath
        if (-not $e) { return $null }
        $sr = New-Object IO.StreamReader($e.Open(), [Text.Encoding]::UTF8)
        $t = $sr.ReadToEnd(); $sr.Close(); return , $t
    } finally { $zip.Dispose() }
}

$ssXml = Get-ZipText $xlsx "xl/sharedStrings.xml"
$d = New-Object System.Xml.XmlDocument; $d.LoadXml($ssXml)
$ns = New-Object System.Xml.XmlNamespaceManager($d.NameTable)
$ns.AddNamespace("a", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
$ss = @(); foreach ($si in $d.SelectNodes("//a:si", $ns)) { $ss += $si.InnerText }

$wbXml = Get-ZipText $xlsx "xl/workbook.xml"
$sheetList = @()
foreach ($m in [regex]::Matches($wbXml, '<sheet[^>]*name="([^"]*)"[^>]*r:id="rId(\d+)"')) {
    $sheetList += @{ name = $m.Groups[1].Value; n = [int]$m.Groups[2].Value }
}

function Get-RowCells($doc, $ns) {
    $map = @{}
    foreach ($row in $doc.SelectNodes("//a:row", $ns)) {
        foreach ($c in $row.SelectNodes("a:c", $ns)) {
            $ref = $c.GetAttribute("r")
            if ($ref -notmatch '^([A-Z]+)(\d+)$') { continue }
            $col = $Matches[1]; $rn = [int]$Matches[2]
            $t = $c.GetAttribute("t")
            $v = $c.SelectSingleNode("a:v", $ns)
            $val = ''; if ($v) { $val = $v.InnerText }
            if ($t -eq 's' -and $val -ne '') { $val = $ss[[int]$val] }
            elseif ($t -eq 'inlineStr') { $val = $c.SelectSingleNode("a:is", $ns).InnerText }
            if ($val -ne '') { if (-not $map.ContainsKey($rn)) { $map[$rn] = @{} }; $map[$rn][$col] = $val }
        }
    }
    return $map
}

$risks = @(); $extraSheets = @()
foreach ($sh in $sheetList) {
    $xml = Get-ZipText $xlsx "xl/worksheets/sheet$($sh.n).xml"
    $doc = New-Object System.Xml.XmlDocument; $doc.LoadXml($xml)
    $rows = Get-RowCells $doc $ns

    $labelRow = @{}
    foreach ($rn in ($rows.Keys | Sort-Object)) {
        foreach ($col in $rows[$rn].Keys) {
            $txt = $rows[$rn][$col]
            foreach ($lab in $labels.labels) {
                if ($txt.StartsWith($lab) -and -not $labelRow.ContainsKey($lab)) { $labelRow[$lab] = @{ row = [int]$rn; col = $col } }
            }
        }
    }
    $find = { param($k) if ($labelRow.ContainsKey($k)) { $labelRow[$k] } else { $null } }
    $L = $labels.keyLabels
    $sigLab = & $find $L.signalIds
    if (-not $sigLab) {
        $flat = @()
        foreach ($rn in ($rows.Keys | Sort-Object)) {
            foreach ($col in ($rows[$rn].Keys | Sort-Object)) { $flat += @{ cell = "$col$rn"; text = $rows[$rn][$col] } }
        }
        $extraSheets += @{ name = $sh.name; cells = $flat }
        continue
    }

    $sigRow = [int]$sigLab.row
    $sigCols = @(); foreach ($col in ($rows[$sigRow].Keys | Sort-Object)) { if ($col -ne $sigLab.col) { $sigCols += $col } }
    $fLab  = & $find $L.formula
    $srcLab= & $find $L.dataSource
    $thLab = & $find $L.threshold
    $kwLab = & $find $L.keywords
    $evLab = & $find $L.evidence
    $nmLab = & $find $L.signalNames
    $tyLab = & $find $L.signalTypes

    $riskLab = & $find $L.riskId
    $metaCol = ''
    foreach ($c2 in ($rows[[int]$riskLab.row].Keys | Sort-Object)) { if ($c2 -ne $riskLab.col) { $metaCol = $c2; break } }
    if (-not $metaCol) { $metaCol = $sigLab.col }
    $riskId  = $rows[[int]$riskLab.row][$metaCol]
    $riskName = $rows[[int](& $find $L.riskName).row][$metaCol]
    $category = $rows[[int](& $find $L.category).row][$metaCol]
    $definition = $rows[[int](& $find $L.definition).row][$metaCol]
    if (-not $riskId) { $riskId = $sh.name }

    $clean = { param($s)
        $s = $s -replace '^[\s\u3000]*', ''
        $s = $s -replace '[\s\u3000]*$', ''
        $s = $s -replace '\uff1b\s*$', ''
        $s = $s -replace '\s+', ' '
        $s = $s.Trim()
        if ($s -match '^[\.\u2026\-\u2014~\s]{1,8}$') { return '' }
        return $s
    }.GetNewClosure()
    $stripNum = { param($s) ($s -replace '^\s*\d+[\.\u3001\uff0e]\s*', '') -replace '^\s*#+\s*', '' }.GetNewClosure()
    $nameOf = { param($s)
        $s = & $stripNum $s
        if ($s -match '^([^=\uff1d]+?)\s*[\=\uff1d]') { $s = $Matches[1] }
        return ($s -replace '^\s+|\s+$', '').Trim()
    }.GetNewClosure()
    $normSigId = { param($s)
        $m1 = [regex]::Match($s, 'R0\d{2}'); $m2 = [regex]::Match($s, 'S\d{2}')
        if ($m1.Success -and $m2.Success) { return ($m1.Value + '-' + $m2.Value) }
        return ($s -replace '^\s+|\s+$', '')
    }.GetNewClosure()
    $cellRows = { param($col, $from, $to)
        # non-empty contiguous run inside [from..to], longest block anchored at first hit
        $hits = @()
        for ($r = $from; $r -le $to; $r++) {
            if ($rows.ContainsKey($r) -and $rows[$r].ContainsKey($col)) {
                $c2 = & $clean $rows[$r][$col]
                if ($c2) { $hits += @{ row = $r; text = $c2 } }
            }
        }
        $out = @()
        if ($hits.Count) {
            $start = $hits[0].row
            foreach ($it in $hits) { if ($it.row -le $start + $out.Count) { $out += $it.text } }
        }
        return , $out
    }.GetNewClosure()

    # next label row strictly after a given row -> used to bound a region
    $labelRowNos = @($labelRow.Values | ForEach-Object { [int]$_.row } | Sort-Object)
    $nextLabelAfter = { param($r)
        foreach ($lr in $labelRowNos) { if ($lr -gt $r) { return $lr } }
        return $r + 40
    }.GetNewClosure()

    # split a merged formula cell into segments: numbered items first, then
    # un-numbered "name = ... name2 = ..." runs (single-space separated)
    $splitFormulaCell = { param($s)
        $segs = @(); $cur = ''
        foreach ($tk in [regex]::Split($s, '(\n|\uff1b|;)')) {
            if ($tk -match '^\s*\d+[\.\u3001\uff0e]') { if ($cur.Trim()) { $segs += $cur.Trim() }; $cur = $tk } else { $cur += $tk }
        }
        if ($cur.Trim()) { $segs += $cur.Trim() }
        if ($segs.Count -le 1) {
            $ms = [regex]::Matches($s, '(?<=\s)\d+[\.\u3001\uff0e]')
            if ($ms.Count -ge 1) {
                $segs = @(); $idx = 0
                foreach ($mm in $ms) { $segs += $s.Substring($idx, $mm.Index - $idx).Trim(); $idx = $mm.Index }
                $segs += $s.Substring($idx).Trim()
                $segs = @($segs | Where-Object { $_ })
            }
        }
        if ($segs.Count -le 1) {
            # un-numbered multi-formula cell: split before a following 'name=' token
            $m2 = [regex]::Matches($s, '(?<=\S)\s+(?=\S{1,28}?=)')
            if ($m2.Count -ge 1) {
                $segs = @(); $idx = 0
                foreach ($mm in $m2) { $segs += $s.Substring($idx, $mm.Index - $idx).Trim(); $idx = $mm.Index }
                $segs += $s.Substring($idx).Trim()
                $segs = @($segs | Where-Object { $_ -match '=' })
                if (-not $segs.Count) { $segs = @($s) }
            }
        }
        return , $segs
    }.GetNewClosure()

    # ---- sheet-level tier-matrix detection ----
    # tier matrix: the threshold area of the FIRST signal column holds only tier
    # words (tier words); descriptions are shifted one column to the right,
    # i.e. description for signal at position p lives in column at position p+1.
    $tierModeSheet = $false
    $sigCount0 = $sigCols.Count
    if ($thLab -and $sigCount0 -ge 2) {
        $probeFrom = [int]$thLab.row
        $probeTo = if ($kwLab) { [int]$kwLab.row - 1 } else { $probeFrom + 3 }
        if ($thLab) { $probeTo = [Math]::Min($probeTo, ((& $nextLabelAfter $probeFrom) - 1)) }
        $c0 = $sigCols[0]
        $probe = @()
        for ($r = $probeFrom; $r -le $probeTo; $r++) {
            if ($rows.ContainsKey($r) -and $rows[$r].ContainsKey($c0)) {
                $c2 = & $clean $rows[$r][$c0]
                if ($c2) { $probe += $c2 }
            }
        }
        $wordHits = @($probe | Where-Object { $labels.tierWords -contains $_ })
        if ($probe.Count -ge 2 -and $wordHits.Count -ge [Math]::Min(3, $probe.Count)) { $tierModeSheet = $true }
    }

    $signals = @()
    $sigIdx = 0
    foreach ($col in $sigCols) {
        $sigIdx++
        $sigId = & $normSigId $rows[$sigRow][$col]
        $sigName = ''; if ($nmLab) { $sigName = $rows[[int]$nmLab.row][$col] }
        $sigType = ''; if ($tyLab) { $sigType = $rows[[int]$tyLab.row][$col] }
        $src = ''; if ($srcLab) { $src = $rows[[int]$srcLab.row][$col] }
        $kw  = ''; if ($kwLab)  { $kw  = $rows[[int]$kwLab.row][$col] }
        $ev  = ''; if ($evLab)  { $ev  = $rows[[int]$evLab.row][$col] }
        if ($sigName) { $sigName = (& $clean $sigName) }
        if ($sigType) { $sigType = (& $clean $sigType) }
        if ($kw)      { $kw = $kw.Trim() }
        if ($ev)      { $ev = $ev.Trim() }

        # formula region: [formula-label row .. next label row - 1]
        $fFrom = if ($fLab) { [int]$fLab.row } else { $sigRow + 2 }
        $fTo   = (& $nextLabelAfter $fFrom) - 1
        $formulas = & $cellRows $col $fFrom $fTo

        # merged single cell carrying several numbered items?
        $merged = $false
        if ($formulas.Count -eq 1) {
            $segs0 = & $splitFormulaCell $formulas[0]
            if ($segs0.Count -ge 2) { $merged = $true }
        }

        # threshold region: [threshold-label row .. next label row - 1]
        $thFrom = if ($thLab) { [int]$thLab.row } elseif ($srcLab) { [int]$srcLab.row + 1 } else { $fTo + 1 }
        $thTo   = if ($kwLab) { [int]$kwLab.row - 1 } else { $thFrom + 15 }
        if ($thLab) { $thTo = [Math]::Min($thTo, ((& $nextLabelAfter $thFrom) - 1)) }
        $thRows = @()
        for ($r = $thFrom; $r -le $thTo; $r++) {
            if ($rows.ContainsKey($r) -and $rows[$r].ContainsKey($col)) {
                $c2 = & $clean $rows[$r][$col]
                if ($c2) { $thRows += @{ row = $r; text = $c2 } }
            }
        }
        $thresholds = @()
        if ($thRows.Count) {
            $start = $thRows[0].row
            foreach ($it in $thRows) { if ($it.row -le $start + $thresholds.Count) { $thresholds += $it.text } }
        }

        # ---------- build indicators ----------
        $indicators = @()
        if ($merged -and -not $tierModeSheet) {
            # split merged formula cell
            $fList = @()
            foreach ($p in (& $splitFormulaCell $formulas[0])) { $c2 = & $clean $p; if ($c2) { $fList += $c2 } }
            # thresholds: same style split
            $tAll = @()
            foreach ($th in $thresholds) {
                $tp = @(); $c2 = ''
                foreach ($tk in [regex]::Split($th, '(\n|\uff1b|;)')) {
                    if ($tk -match '^\s*\d+[\.\u3001\uff0e]') { if ($c2.Trim()) { $tp += $c2.Trim() }; $c2 = $tk } else { $c2 += $tk }
                }
                if ($c2.Trim()) { $tp += $c2.Trim() }
                $tAll += $tp
            }
            if ($tAll.Count -eq $fList.Count) {
                for ($i = 0; $i -lt $fList.Count; $i++) {
                    $f = & $stripNum $fList[$i]
                    $indicators += @{ name = (& $nameOf $f); formula = $f; threshold = (& $stripNum $tAll[$i]) }
                }
            } else {
                for ($i = 0; $i -lt $fList.Count; $i++) {
                    $f = & $stripNum $fList[$i]
                    $indicators += @{ name = (& $nameOf $f); formula = $f; threshold = '' }
                }
            }
        }
        elseif ($tierModeSheet) {
            # tier matrix: description for the signal at position p lives in the
            # column at position p+1 (author shifted the matrix one column right).
            $sigPos = [Array]::IndexOf($sigCols, $col)
            $descIdx = $sigPos + 1
            $descCol = if ($descIdx -lt $sigCols.Count) { $sigCols[$descIdx] } else { '' }
            $oneTh = ''
            if ($descCol) {
                $wordByRow = @{}
                $wCol = $sigCols[0]
                for ($r = $thFrom; $r -le $thTo; $r++) {
                    if ($rows.ContainsKey($r) -and $rows[$r].ContainsKey($wCol)) {
                        $w2 = & $clean $rows[$r][$wCol]
                        if ($labels.tierWords -contains $w2) { $wordByRow[$r] = $w2 }
                    }
                }
                $descRows = @()
                for ($r = $thFrom; $r -le $thTo; $r++) {
                    if ($rows.ContainsKey($r) -and $rows[$r].ContainsKey($descCol)) {
                        $c2 = & $clean $rows[$r][$descCol]
                        if ($c2) { $descRows += @{ row = $r; text = $c2 } }
                    }
                }
                $pairs = @()
                foreach ($it in $descRows) {
                    $w3 = if ($wordByRow.ContainsKey($it.row)) { $wordByRow[$it.row] } else { '' }
                    if ($w3) { $pairs += ($w3 + [string][char]0xFF1A + $it.text) }
                }
                if ($pairs.Count) { $oneTh = $pairs -join (' ' + [string][char]0xFF1B + ' ') }
            }
            # formulas may still be one merged cell -> split them
            if ($formulas.Count -eq 1) {
                $segs1 = & $splitFormulaCell $formulas[0]
                if ($segs1.Count -ge 2) { $formulas = @(); foreach ($p in $segs1) { $c3 = & $clean $p; if ($c3) { $formulas += $c3 } } }
            }
            if (-not $formulas.Count) { $formulas = @('') }
            for ($i = 0; $i -lt $formulas.Count; $i++) {
                $f = & $stripNum $formulas[$i]
                $indicators += @{ name = (& $nameOf $f); formula = $f; threshold = $(if ($i -eq 0) { $oneTh } else { '' }) }
            }
        }
        else {
            $n = [Math]::Max($formulas.Count, $thresholds.Count)
            for ($i = 0; $i -lt $n; $i++) {
                $f = if ($i -lt $formulas.Count) { (& $stripNum $formulas[$i]) } else { '' }
                $t = if ($i -lt $thresholds.Count) { $thresholds[$i] } else { '' }
                $indicators += @{ name = (& $nameOf $f); formula = $f; threshold = $t }
            }
        }
        # signal-level text of all thresholds of this signal (for prompts/UI)
        $sigThText = ''
        $thParts = @()
        if ($merged) {
            $thParts = @($indicators | ForEach-Object { if ($_.threshold) { $_.threshold } })
            if (-not $thParts.Count) { $thParts = @($thresholds | Where-Object { $_ }) }
        } elseif ($tierModeSheet) {
            if ($indicators.Count) { $thParts = @($indicators[0].threshold) }
        } else {
            if ($thresholds.Count) { $thParts = @($thresholds | Where-Object { $_ }) }
            else { $thParts = @($indicators | ForEach-Object { if ($_.threshold) { $_.threshold } }) }
        }
        if ($thParts.Count) { $sigThText = $thParts -join (' ' + [string][char]0xFF1B + ' ') }
        # signal-level extra thresholds not paired into indicators
        $extra = @()
        if (-not $merged -and -not $tierModeSheet) {
            for ($i = $formulas.Count; $i -lt $thresholds.Count; $i++) { $extra += $thresholds[$i] }
        }
        $signals += @{
            id = $sigId; name = $sigName; type = $sigType
            dataSource = $src; keywords = $kw; evidence = $ev
            indicators = $indicators; extraThresholds = $extra; thresholdText = $sigThText
        }
    }
    # risk id may be a stale template copy in some sheets -> trust the signal-id prefix
    if ($signals.Count -and $signals[0].id -match '^(R0\d{2})-') {
        $realId = $Matches[1]
        if ($realId -ne $riskId) { $riskId = $realId }
    }
    $risks += @{
        id = $riskId; name = $riskName; category = $category; definition = $definition
        signals = $signals
    }
}

$totalSig = 0; $totalInd = 0
foreach ($r in $risks) { $totalSig += $r.signals.Count; foreach ($s in $r.signals) { $totalInd += $s.indicators.Count } }
$result = @{
    meta = @{ source = 'AnnualReportRiskRuleBase V1.0'; builtBy = 'scripts/build_rules.ps1'; counts = @{ risks = $risks.Count; signals = $totalSig; indicators = $totalInd } }
    risks = $risks
    extraSheets = $extraSheets
}
[IO.File]::WriteAllText($out, ($result | ConvertTo-Json -Depth 30), $utf8)
Write-Output ("OK risks={0} signals={1} indicators={2} extraSheets={3}" -f $risks.Count, $totalSig, $totalInd, $extraSheets.Count)

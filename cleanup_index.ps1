# Read the file
$lines = Get-Content "frontend\index.html" -Raw
$allLines = Get-Content "frontend\index.html"
$total = $allLines.Count

Write-Host "Total lines: $total"

# We need to keep:
# Lines 1-2264 (head + CSS + hero section end)
# Lines 2291-2344 (process section) -- but skip 2266-2289 (ticker)
# Lines 2405-2481 (features section)
# Lines 2645-2673 (testimonials section)
# Lines 2675-2788 (FAQ section)
# Lines 3473-3514 (network section) -- but these lines shifted due to bad edit
# Lines 3515-end (back-to-top, cookie, help, footer, JS)

# Because of the bad edit, let me find the actual network section by content
$networkStart = -1
$networkEnd = -1
$footerStart = -1
for ($i = 0; $i -lt $total; $i++) {
    if ($allLines[$i] -match 'id="network".*bg-dark.*text-white') {
        $networkStart = $i
    }
    if ($networkStart -gt 0 -and $networkEnd -lt 0 -and $allLines[$i] -match 'id="stationsList"') {
        # Found stations list, look for closing section
    }
    if ($networkStart -gt 0 -and $networkEnd -lt 0 -and $i -gt $networkStart + 5 -and $allLines[$i].Trim() -eq '</section>') {
        # Check if this is the network section's closing
        if ($allLines[$i-1].Trim() -match '</div>' -or $allLines[$i-2].Trim() -match '</div>') {
            $networkEnd = $i
        }
    }
}

Write-Host "Network section found at lines: $($networkStart+1) to $($networkEnd+1)"

# Let's just find key markers
for ($i = 0; $i -lt $total; $i++) {
    $line = $allLines[$i].Trim()
    if ($line -match '<!-- ============ FLOATING HELP') {
        Write-Host "Floating Help at line: $($i+1)"
    }
    if ($line -match '<!-- ============ FOOTER') {
        Write-Host "Footer at line: $($i+1)"
    }
    if ($line -match 'id="backToTop"') {
        Write-Host "BackToTop at line: $($i+1)"
    }
    if ($line -match 'id="cookieBanner"') {
        Write-Host "Cookie Banner at line: $($i+1)"
    }
    if ($line -match 'id="stationsList"') {
        Write-Host "Stations List at line: $($i+1)"
    }
}

[CmdletBinding()]
param([string]$Distro = 'Ubuntu', [string]$LinuxUser = 'coope')

$ErrorActionPreference = 'Stop'
$configPath = Join-Path $env:USERPROFILE '.wslconfig'
$content = if (Test-Path -LiteralPath $configPath) {
    [IO.File]::ReadAllText($configPath)
} else { '' }

# Update only the general section; preserve existing VM and networking settings.
$sectionPattern = '(?ms)^\[general\][^\S\r\n]*\r?\n(?<body>.*?)(?=^\[|\z)'
$section = [regex]::Match($content, $sectionPattern)
if ($section.Success) {
    $body = $section.Groups['body'].Value
    $keyPattern = '(?m)^\s*instanceIdleTimeout\s*=.*$'
    if ([regex]::IsMatch($body, $keyPattern)) {
        $body = [regex]::Replace($body, $keyPattern, 'instanceIdleTimeout=-1')
    } else {
        $body = $body.TrimEnd() + "`r`ninstanceIdleTimeout=-1`r`n"
    }
    $updated = $content.Substring(0, $section.Index) + "[general]`r`n" + $body + $content.Substring($section.Index + $section.Length)
} else {
    $updated = $content.TrimEnd() + "`r`n`r`n[general]`r`ninstanceIdleTimeout=-1`r`n"
}
$updated = [regex]::Replace($updated, '\r?\n', "`r`n")
if ($updated -cne $content) {
    if (Test-Path -LiteralPath $configPath) {
        $backup = $configPath + '.clipper-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.bak'
        Copy-Item -LiteralPath $configPath -Destination $backup
        Write-Output "Configuration backup: $backup"
    }
    [IO.File]::WriteAllText($configPath, $updated, [Text.UTF8Encoding]::new($false))
}

# Keep this already-running instance alive without terminating other Linux work.
# The configuration above applies on the next WSL start. The existing Windows
# WSL SSH Bridge boot task already starts Ubuntu after Windows boots.
$wsl = Join-Path $env:WINDIR 'System32\wsl.exe'
$keepers = @(& $wsl -d $Distro -u $LinuxUser --exec /usr/bin/pgrep -f '^/usr/bin/sleep infinity$')
if ($LASTEXITCODE -eq 1) {
    $keeper = Start-Process -FilePath $wsl -ArgumentList @('-d', $Distro, '-u', $LinuxUser, '--exec', '/usr/bin/sleep', 'infinity') -WindowStyle Hidden -PassThru
    Write-Output "Started WSL keepalive, Windows PID: $($keeper.Id)"
} elseif ($LASTEXITCODE -ne 0) {
    throw 'Could not check the WSL keepalive process.'
} else {
    Write-Output "WSL keepalive already running: $keepers"
}
Write-Output ([IO.File]::ReadAllText($configPath))

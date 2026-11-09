[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9_.-]+$')][string]$Distro = 'Ubuntu',
    [ValidatePattern('^[A-Za-z0-9_.-]*$')][string]$LinuxUser = ''
)

$ErrorActionPreference = 'Stop'
$wsl = Join-Path $env:WINDIR 'System32\wsl.exe'
if ([string]::IsNullOrWhiteSpace($LinuxUser)) {
    $LinuxUser = (& $wsl -d $Distro --exec /usr/bin/id -un).Trim()
    if ($LinuxUser -notmatch '^[A-Za-z0-9_.-]+$') {
        throw 'Could not safely detect the Linux user. Pass -LinuxUser explicitly.'
    }
}
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

# A scheduled task owns the Windows process independently of SSH and interop
# sessions. A detached child of an SSH-launched PowerShell can still be killed
# when its Windows job ends. The task also restarts after Windows boots.
$taskName = 'Clipper WSL Keepalive'
$arguments = "-d $Distro -u $LinuxUser --exec /usr/bin/sleep infinity"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    if ($task.Actions.Count -ne 1 -or $task.Actions[0].Execute -ne $wsl -or $task.Actions[0].Arguments -ne $arguments) {
        throw "Existing task '$taskName' has a different action; inspect it before updating."
    }
} else {
    $account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute $wsl -Argument $arguments
    $principal = New-ScheduledTaskPrincipal -UserId $account -LogonType S4U -RunLevel Limited
    $startup = New-ScheduledTaskTrigger -AtStartup
    $retry = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $task = Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Trigger @($startup, $retry) -Settings $settings -Description 'Keep Ubuntu Clipper available independently of SSH sessions.'
}
if ($task.State -ne 'Running') { Start-ScheduledTask -TaskName $taskName }
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName $taskName | Select-Object LastRunTime, LastTaskResult
Write-Output ([IO.File]::ReadAllText($configPath))

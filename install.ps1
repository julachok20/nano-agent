# nano Agent installer for native Windows. Runs in the current user account.
# Download and inspect before running: irm https://raw.githubusercontent.com/julachok20/nano-agent/main/install.ps1 | iex
param(
    [switch]$DryRun,
    [switch]$NoSetup,
    [switch]$Yes,
    [string]$From = ''
)

$ErrorActionPreference = 'Stop'
$repo = if ($env:NANO_AGENT_REPO) { $env:NANO_AGENT_REPO } else { 'julachok20/nano-agent' }
$ref = if ($env:NANO_AGENT_REF) { $env:NANO_AGENT_REF } else { 'main' }
$spec = if ($From) { $From } elseif ($env:NANO_AGENT_SPEC) { $env:NANO_AGENT_SPEC } else { "https://codeload.github.com/$repo/tar.gz/$ref" }
$agentHome = if ($env:NANO_AGENT_HOME) { $env:NANO_AGENT_HOME } else { Join-Path $HOME '.nano-agent' }
$binDir = if ($env:NANO_AGENT_BIN_DIR) { $env:NANO_AGENT_BIN_DIR } else { Join-Path $HOME '.local\bin' }
$isInteractive = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected
$esc = [char]27

function Show-Screen([int]$Step, [string]$Title, [string[]]$Details = @()) {
    if (-not $isInteractive -or $env:NO_COLOR) {
        Write-Host "nano Agent / $Title"
        foreach ($detail in $Details) { Write-Host "  $detail" }
        return
    }
    Write-Host "$esc[2J$esc[H" -NoNewline
    Write-Host "`n  $esc[1;38;2;255;112;32m◆$esc[0m  $esc[1;38;2;248;248;246mNANO AGENT$esc[0m  $esc[38;2;125;137;149m/  INSTALLER$esc[0m"
    Write-Host "  $esc[38;2;70;78;88m────────────────────────────────────────────────────────────$esc[0m`n"
    if ([Console]::WindowWidth -ge 58) {
        Write-Host "  $esc[1;38;2;248;248;246m╭╮ ╭╮ ╭──╮ ╭╮ ╭╮ ╭──╮$esc[0m    $esc[1;38;2;255;112;32m╭──╮ ╭──╮ ╭─── ╭╮ ╭╮ ┳━━┳$esc[0m"
        Write-Host "  $esc[1;38;2;248;248;246m│╰╮│ ├──┤ │╰╮│ │  │$esc[0m    $esc[1;38;2;255;112;32m├──┤ │ ╭╮ ├──  │╰╮│   ┃$esc[0m"
        Write-Host "  $esc[1;38;2;248;248;246m╵ ╰╯ ╵  ╵ ╵ ╰╯ ╰──╯$esc[0m    $esc[1;38;2;255;112;32m╵  ╵ ╰──╯ ╰─── ╵ ╰╯   ╵$esc[0m"
    } else { Write-Host "  $esc[1;38;2;248;248;246mNANO $esc[1;38;2;255;112;32mAGENT$esc[0m" }
    Write-Host "`n  $esc[38;2;125;137;149mPERSONAL AI  /  LOCAL FIRST$esc[0m`n"
    $labels = @('CHECK', 'INSTALL', 'SET UP', 'LAUNCH')
    $parts = for ($i = 1; $i -le 4; $i++) {
        if ($i -eq $Step) { "$esc[1;38;2;255;112;32m{0:00} {1}$esc[0m" -f $i, $labels[$i - 1] }
        elseif ($i -lt $Step) { "$esc[38;2;125;185;150m✓ {0}$esc[0m" -f $labels[$i - 1] }
        else { "$esc[38;2;115;128;142m{0:00} {1}$esc[0m" -f $i, $labels[$i - 1] }
    }
    Write-Host ('  ' + ($parts -join "  $esc[38;2;70;78;88m/$esc[0m  "))
    Write-Host "`n  $esc[38;2;70;78;88m────────────────────────────────────────────────────────────$esc[0m"
    Write-Host "  $esc[1;38;2;248;248;246m$Title$esc[0m"
    Write-Host "  $esc[38;2;70;78;88m────────────────────────────────────────────────────────────$esc[0m"
    foreach ($detail in $Details) { Write-Host "  $esc[38;2;190;202;214m$detail$esc[0m" }
    Write-Host ''
}

function Find-Python {
    $candidates = @()
    foreach ($name in @('python', 'python3.13', 'python3.12', 'python3.11', 'python3')) {
        if (Get-Command $name -ErrorAction SilentlyContinue) { $candidates += ,@($name) }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += ,@('py', '-3') }
    foreach ($candidate in $candidates) {
        try {
            $versionArg = if ($candidate.Count -gt 1) { @($candidate[1]) } else { @() }
            $output = & $candidate[0] @versionArg -c 'import sys; print("%d.%d.%d" % sys.version_info[:3]); sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return @{ Command = $candidate; Version = [string]$output } }
        } catch { }
    }
    return $null
}

function Invoke-Python($Selected, [string[]]$Arguments) {
    $command = $Selected.Command
    $pythonArgs = @()
    if ($command.Count -gt 1) { $pythonArgs += $command[1..($command.Count - 1)] }
    & $command[0] @pythonArgs @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python command failed with exit code $LASTEXITCODE" }
}

Show-Screen 1 'Checking this computer…'
$python = Find-Python
if (-not $python) {
    Write-Host 'Python 3.11 or newer was not found.'
    if (-not $DryRun -and $isInteractive -and (Get-Command winget -ErrorAction SilentlyContinue)) {
        $answer = Read-Host 'Install Python 3.12 for your user account with winget? [y/N]'
        if ($answer -match '^(y|yes)$') {
            & winget install --id Python.Python.3.12 --exact --scope user
            if ($LASTEXITCODE -ne 0) { throw 'winget could not install Python.' }
            $python = Find-Python
        }
    }
    if (-not $python) { throw 'Install Python 3.11+ and reopen PowerShell, then run this installer again.' }
}

$method = if (Get-Command uv -ErrorAction SilentlyContinue) { 'uv' } elseif (Get-Command pipx -ErrorAction SilentlyContinue) { 'pipx' } else { 'venv' }
$plan = switch ($method) {
    'uv' { "uv tool install --python $($python.Version) --force $spec" }
    'pipx' { "pipx install --python $($python.Version) --force $spec" }
    default { "Create $agentHome\venv; pip install $spec; link $binDir\nano-agent.exe" }
}
Show-Screen 2 'Ready to install' @(
    "OS: Windows · Python: $($python.Version)",
    "Source: $spec",
    "Method: $method · Data: $agentHome",
    "Will run: $plan",
    'Next: install package → configure assistant → open console',
    'No admin rights or shell-profile changes.'
)
if ($DryRun) { Write-Host 'dry run: nothing was changed.'; return }
if (-not $Yes -and $isInteractive) {
    $answer = Read-Host '  ›  Press Enter to install (n to cancel)'
    if ($answer -match '^(n|no)$') { Write-Host 'aborted.'; return }
}

Show-Screen 2 "Installing nano Agent with $method…"
switch ($method) {
    'uv' {
        & uv tool install --python $python.Version --force $spec
        if ($LASTEXITCODE -ne 0) { throw 'uv install failed.' }
        $agent = (Get-Command nano-agent -ErrorAction SilentlyContinue).Source
        if (-not $agent) { $agent = Join-Path $binDir 'nano-agent.exe' }
    }
    'pipx' {
        & pipx install --python $python.Version --force $spec
        if ($LASTEXITCODE -ne 0) { throw 'pipx install failed.' }
        $agent = (Get-Command nano-agent -ErrorAction SilentlyContinue).Source
        if (-not $agent) { $agent = Join-Path $binDir 'nano-agent.exe' }
    }
    'venv' {
        New-Item -ItemType Directory -Force -Path $agentHome, $binDir | Out-Null
        Invoke-Python $python @('-m', 'venv', (Join-Path $agentHome 'venv'))
        $venvPython = Join-Path $agentHome 'venv\Scripts\python.exe'
        & $venvPython -m pip install --disable-pip-version-check --quiet $spec
        if ($LASTEXITCODE -ne 0) { throw 'pip install failed.' }
        $agent = Join-Path $agentHome 'venv\Scripts\nano-agent.exe'
        $launcher = Join-Path $binDir 'nano-agent.cmd'
        Set-Content -Path $launcher -Encoding Ascii -Value "@echo off`r`n`"$agent`" %*"
    }
}
if (-not (Test-Path -LiteralPath $agent)) { throw "Installation finished but $agent was not found." }
& $agent --version
if ($LASTEXITCODE -ne 0) { throw 'The installed command did not run.' }
if ($method -eq 'venv' -and -not (($env:PATH -split ';') -contains $binDir)) {
    Write-Host "Command launcher: $launcher (add $binDir to PATH later if you want 'nano-agent' everywhere)."
}
if ($NoSetup) { Write-Host 'Installed. Next: nano-agent setup'; return }
if ($isInteractive) {
    Show-Screen 3 'Installation complete · opening setup…'
    & $agent setup
    if ($LASTEXITCODE -ne 0) { throw 'Setup did not finish.' }
} else {
    Write-Host "Installed. Run: $agent setup"
}

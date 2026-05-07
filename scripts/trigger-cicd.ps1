param(
    [ValidateSet("ci", "release")]
    [string]$Workflow = "ci",

    [string]$Version = "",
    [string]$Ref = "",
    [string]$CommitMessage = "Prepare production CI/CD",

    [switch]$NoCommit,
    [switch]$NoPush,
    [switch]$NoWatch,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Refresh-Path {
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Invoke-Checked {
    param(
        [string]$Tool,
        [string[]]$Arguments
    )

    & $Tool @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Tool $($Arguments -join ' ')"
    }
}

function Test-GitHubAuth {
    $ghPath = (Get-Command gh).Source
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $ghPath
    $startInfo.Arguments = "auth status"
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $process.WaitForExit()

    return $process.ExitCode -eq 0
}

Refresh-Path

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not installed or not on PATH."
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI is not installed or not on PATH. Install it with: winget install --id GitHub.cli --source winget"
}

Write-Step "Checking GitHub authentication"
if (-not (Test-GitHubAuth)) {
    Write-Host "GitHub CLI is not authenticated. Opening browser login..." -ForegroundColor Yellow
    Invoke-Checked "gh" @("auth", "login", "--web")
}

if (-not $Ref) {
    $Ref = git branch --show-current
}

if (-not $Ref) {
    throw "Could not determine the current Git branch. Pass -Ref explicitly."
}

$repo = gh repo view --json nameWithOwner --jq ".nameWithOwner"
if (-not $repo) {
    throw "Could not resolve the GitHub repository. Make sure this folder has a GitHub remote."
}

$workflowName = if ($Workflow -eq "release") { "Release" } else { "CI" }

if ($Workflow -eq "release" -and -not $Version) {
    $Version = Read-Host "Release version, for example v1.0.0"
}

if ($Workflow -eq "release" -and -not $Version) {
    throw "Release workflow requires a version."
}

Write-Step "Preparing branch '$Ref' for $Workflow workflow"
$status = git status --porcelain
if ($status -and -not $NoCommit) {
    Write-Host "Committing current workspace changes..."
    Invoke-Checked "git" @("add", "-A")
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        Invoke-Checked "git" @("commit", "-m", $CommitMessage)
    } else {
        Write-Host "No staged changes to commit."
    }
} elseif ($status) {
    Write-Host "Workspace has uncommitted changes; leaving them uncommitted because -NoCommit was passed." -ForegroundColor Yellow
} else {
    Write-Host "Workspace is clean."
}

if (-not $NoPush) {
    Write-Step "Pushing '$Ref'"
    $upstream = git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null
    if ($LASTEXITCODE -eq 0 -and $upstream) {
        Invoke-Checked "git" @("push")
    } else {
        Invoke-Checked "git" @("push", "-u", "origin", $Ref)
    }
} else {
    Write-Host "Skipping push because -NoPush was passed." -ForegroundColor Yellow
}

Write-Step "Triggering GitHub Actions workflow '$workflowName'"
if ($Workflow -eq "release") {
    Invoke-Checked "gh" @("workflow", "run", $workflowName, "--repo", $repo, "--ref", $Ref, "-f", "version=$Version")
    Write-Host "Triggered release workflow on '$Ref' for '$Version'."
} else {
    Invoke-Checked "gh" @("workflow", "run", $workflowName, "--repo", $repo, "--ref", $Ref)
    Write-Host "Triggered CI workflow on '$Ref'."
}

Start-Sleep -Seconds 3
$runUrl = gh run list --repo $repo --workflow $workflowName --branch $Ref --limit 1 --json url --jq ".[0].url"

if ($runUrl) {
    Write-Host "Run URL: $runUrl" -ForegroundColor Green
}

if (-not $NoOpen -and $runUrl) {
    Start-Process $runUrl
}

if (-not $NoWatch) {
    Write-Step "Watching workflow run"
    Invoke-Checked "gh" @("run", "watch", "--repo", $repo)
}

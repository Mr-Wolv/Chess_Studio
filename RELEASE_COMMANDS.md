# Release Commands

This document collects the common commands used to validate, build, and publish Chess Studio. The commands assume PowerShell is running from the repository root.

## CI And Release

CI and release are separate GitHub Actions workflows.

| Workflow | Purpose | Result |
| --- | --- | --- |
| CI | Validates source files, checks assets, fetches Stockfish 18, and builds a Windows executable artifact. | Build artifact only |
| Release | Fetches Stockfish 18, builds `ChessStudio.exe`, packages release files, and publishes a versioned GitHub release ZIP. | Public GitHub release |

The release workflow builds the application independently. A separate manual CI run is not required before release, although confirming CI on the target branch is the safer release habit after code changes.

## Prerequisites

GitHub CLI must be installed and authenticated.

```powershell
gh auth login
```

The helper script can also open the authentication flow automatically when needed:

```powershell
.\scripts\trigger-cicd.ps1
```

## Trigger CI

Default behavior:

- Commit current changes.
- Push the current branch.
- Trigger the CI workflow.
- Open the GitHub Actions run in the browser.
- Watch the run in the terminal.

```powershell
.\scripts\trigger-cicd.ps1
```

| Goal | Command |
| --- | --- |
| Trigger CI without committing current changes | `.\scripts\trigger-cicd.ps1 -NoCommit` |
| Trigger CI without pushing | `.\scripts\trigger-cicd.ps1 -NoPush` |
| Trigger CI without opening the browser | `.\scripts\trigger-cicd.ps1 -NoOpen` |
| Trigger CI without watching the run | `.\scripts\trigger-cicd.ps1 -NoWatch` |
| Trigger CI from a specific branch | `.\scripts\trigger-cicd.ps1 -Ref main` |
| Trigger CI with a custom commit message | `.\scripts\trigger-cicd.ps1 -CommitMessage "Prepare Chess Studio release"` |

## Trigger Release

Default release command:

```powershell
.\scripts\trigger-cicd.ps1 -Workflow release -Version v1.0.0
```

| Goal | Command |
| --- | --- |
| Release with a custom commit message | `.\scripts\trigger-cicd.ps1 -Workflow release -Version v1.0.0 -CommitMessage "Release v1.0.0"` |
| Release from a specific branch | `.\scripts\trigger-cicd.ps1 -Workflow release -Version v1.0.0 -Ref main` |
| Release without committing current changes | `.\scripts\trigger-cicd.ps1 -Workflow release -Version v1.0.0 -NoCommit` |
| Release without pushing | `.\scripts\trigger-cicd.ps1 -Workflow release -Version v1.0.0 -NoPush` |
| Release without opening the browser | `.\scripts\trigger-cicd.ps1 -Workflow release -Version v1.0.0 -NoOpen` |
| Release without watching the run | `.\scripts\trigger-cicd.ps1 -Workflow release -Version v1.0.0 -NoWatch` |

## Local Production Build

Local builds do not create GitHub releases. They are useful for checking the executable before pushing or publishing.

| Goal | Command |
| --- | --- |
| Build locally with Stockfish bundled if `AI.exe` exists | `.\scripts\build.ps1 -Clean` |
| Fetch Stockfish 18 first, then bundle it | `.\scripts\build.ps1 -Clean -FetchEngine` |
| Force a bundled-engine build and fail if `AI.exe` is missing | `.\scripts\build.ps1 -Clean -BundleEngine` |
| Fetch Stockfish 18 and force a bundled-engine build | `.\scripts\build.ps1 -Clean -FetchEngine -BundleEngine` |
| Create an engine-less development build | `.\scripts\build.ps1 -Clean -NoBundleEngine` |

The local executable is written to:

```text
dist/ChessStudio.exe
```

## Version Naming

Release versions should use tags such as:

```text
v1.0.0
v1.0.1
v1.1.0
```

Existing release tags should not be reused unless the existing release is intentionally being updated, deleted, or recreated.

## Recommended Release Flow

A. Confirm the application works locally.
B. Trigger CI:

```powershell
.\scripts\trigger-cicd.ps1
```

C. Wait for CI to pass.
D. Trigger release:

```powershell
.\scripts\trigger-cicd.ps1 -Workflow release -Version v1.0.0
```

E. Download the release ZIP from GitHub Releases and smoke-test `ChessStudio.exe`.

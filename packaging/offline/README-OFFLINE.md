# DeepPanda AI Offline Bundle

This folder is a portable Docker deployment for Windows x64 with Docker Desktop using Linux containers.

## Requirements

- Docker Desktop with the WSL 2 backend and Docker Compose v2.20 or newer.
- Linux/amd64 container support.
- About 70 GB free in Docker's storage and enough space to keep this bundle. The current model set makes the bundle roughly 60 GB.
- 32 GB RAM is recommended for the bundled Qwen3.6 model. Ollama is configured to load one model at a time.

Docker Desktop itself is not included and must already be installed. The bundle contains the application images, Ollama image, Qdrant/Redis images, all four persistent data volumes, and a workspace source snapshot. It does not need internet access during installation.

## Install

1. Copy the complete `DeepPanda-Offline-Portable` folder to the target PC and extract it if it was archived.
2. Start Docker Desktop and wait for the Linux engine to be ready.
3. Open PowerShell in this folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\Install-OfflineBundle.ps1
```

The installer verifies every file against `SHA256SUMS.txt`, checks the Docker platform, refuses to overwrite existing `deeppanda-offline_*` volumes, loads the local images, restores the model/data volumes, and starts Compose with pulls/builds disabled.

Open the app at `http://127.0.0.1:8788/` or the PE Workbench at `http://127.0.0.1:8788/pe-lab.html`. API health is at `http://127.0.0.1:8787/api/health`.

## Stop and remove

Stop and remove containers while keeping all models/data:

```powershell
.\Remove-OfflineBundle.ps1
```

To permanently remove model weights and all data volumes, explicitly add `-DeleteData`; the script asks you to type `DELETE`.

## Build this bundle

On the source PC, ensure all five images and four named volumes are present. The builder requires 70 GB free at the output path. For a consistent snapshot of live models/databases, it stops the five services and starts them again automatically in a `finally` block:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\packaging\offline\Build-OfflineBundle.ps1 -PauseServices
```

The output defaults to `%USERPROFILE%\Desktop\DeepPanda-Offline-Portable`. The script never deletes source volumes or any existing output directory. Copy the entire output folder to the target computer.
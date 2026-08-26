# SafeStageWX Agent Workspace Instructions

This file contains key environment and Git authentication instructions for Antigravity AI agents pairing in this repository.

## Git Configuration & Authentication
*   **Active Identity**: Mariana Scott (`felix1028`)
*   **Git User Config**:
    *   Name: `felix1028`
    *   Email: `mfscott28@gmail.com`
*   **Authentication Method**: SSH key-based authentication (`git@github.com:felix1028/buildwithgemini-safestagewx.git`).
    *   The SSH private key is located at `/Users/marianascott/.ssh/id_rsa` on `Mariana's MacBook Pro`.
    *   Always use the SSH remote URL (`git@github...`) for git pushes rather than HTTPS.

## Project Running Details
*   **GCP Project**: `safestagewx`
*   **GCS Bucket**: `safestagewx-static-assets`
*   **Local Backend Port**: `8080` (runs the agent via `uvx google-agents-cli playground` or `uv run agents-cli playground`)
*   **Local Frontend Port**: `8081` (runs the custom frontend proxy via `uv run python3 frontend/main.py`)

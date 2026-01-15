# Ghost Flow MVP v1.1 - Setup & Usage Guide

## 1. Prerequisites

*   **macOS** (12.0 Monterey or newer recommended).
*   **Python 3.9+** installed.
    *   Check by running `python3 --version` in Terminal.
    *   If missing, install via Homebrew: `brew install python`

## 2. Installation

1.  Place all source files (`src/`, `requirements.txt`, `run_ghost_flow.sh`) in a folder, e.g., `~/GhostFlow`.
2.  Open your **Terminal**.
3.  Navigate to the folder:
    ```bash
    cd ~/GhostFlow
    ```
4.  Make the setup script executable:
    ```bash
    chmod +x run_ghost_flow.sh
    ```

## 3. Running the App

Run the automated script. This handles creating the virtual environment and installing dependencies for you.

```bash
./run_ghost_flow.sh

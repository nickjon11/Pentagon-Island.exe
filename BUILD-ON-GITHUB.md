# Pentagon Island v1.0.0 — automated installer build

This package contains the full v1.0.0 source and `.github/workflows/build-installer.yml`.

## One-time setup
1. Commit all files, including the hidden `.github` folder, to your GitHub repository on a test branch.
2. Open **Actions** → **Build Pentagon Island v1.0.0 Installer** → **Run workflow**.
3. After the workflow succeeds, open its run → **Artifacts** → download `PentagonIsland-Setup-v1.0.0`.
4. Unzip the artifact and double-click `PentagonIsland-Setup-v1.0.0.exe` on Windows.

The installer offers an optional desktop shortcut (unchecked by default), Start Menu shortcut, uninstaller, and launch-after-install option. End users do not need Python, Inno Setup, or a .bat file.

**Note:** This is source and an automated Windows build workflow, NOT a precompiled installer. GitHub Actions must run successfully to produce the EXE. The installer has not been tested here on Windows. The workflow does not automatically publish a release.

# Pentagon Island v1.0.0 — Installer Test Kit

This is a **Windows build kit**, not a precompiled installer. It is based on the v0.9.0 Internet Multiplayer Preview.

## Build on Windows 10/11 x64

1. Install Python 3.13 x64 from https://python.org (with Python launcher).
2. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php.
3. Extract the ZIP, then double-click `build-installer-windows.bat` in the project folder.
4. The finished installer will be `release\PentagonIsland-Setup-v1.0.0.exe`.

## Test

1. Double-click the generated installer; follow the classic wizard.
2. Optionally enable a desktop shortcut, then finish installation.
3. Launch from Start Menu > Pentagon Island. No terminal or Python installation needed for players.
4. Test room creation, gameplay, AI, and closing/reopening the game.
5. Uninstall from Windows Settings > Apps.

## Current limitations

- This build packages the **local desktop game**; it does **not yet** automatically launch the Cloudflare Tunnel for internet hosting. That remains a separate v1.0.0 milestone.
- This test installer is unsigned and may prompt Windows SmartScreen.
- The build requires Python and Inno Setup only on the developer's Windows PC, not on players' computers.
- Pywebview may require the Microsoft WebView2 Runtime on the destination PC.
- Do not distribute just the PyInstaller EXE from the `dist` folder without its `_internal` folder. The Inno Setup installer includes the entire folder.

# Pentagon Island v0.9.0 — Internet Multiplayer Preview

This is a **test build**, not a finished production release or compiled Windows EXE. It is based on the v0.8.3 Dark Default archive. The game backend and existing gameplay are retained.

## Host (Machine 1)
1. Install Python and requirements: `python -m pip install -r requirements.txt`.
2. Install `cloudflared` and ensure it is on PATH (Cloudflare Tunnel CLI).
3. From the project directory run `python -m desktop.host_internet`.
4. Open `http://127.0.0.1:8765` in a browser, create a game and copy its room code.
5. Copy the printed `https://...trycloudflare.com` URL.

## Join (Machine 2, including Proton VPN)
Open `docs/index.html` via GitHub Pages after deploying docs/ (or serve docs locally with `python -m http.server 8080 --directory docs`). Enter the HTTPS host URL in **INTERNET MULTIPLAYER**, click Connect to Host, then enter the room code. Browser assets are served from the static site; API/WebSocket requests go to the host URL.

## GitHub Pages
In repository Settings → Pages select **Deploy from a branch**, `main`, `/docs` after testing and merging. The static frontend will be at `https://nickjon11.github.io/Pentagon-Island.exe/` if Pages is enabled for that repository. Do not publish this preview before testing.

## Windows application
Existing `build-windows.bat` packages the local desktop client. The automatic tunnel hosting interface is **not yet integrated** into the EXE; the CLI host helper is the first internet test. GitHub Releases can distribute the compiled Windows application once tested.

## Security and limitations
Quick Tunnels are intended for testing; temporary URLs change and availability is not guaranteed. Room codes alone do not authenticate users; do not expose personal files or services. This preview has not yet undergone remote-network gameplay testing. Browser-based game hosting is not included. The tunnel ends when the host closes it. CORS is limited to the intended GitHub Pages origin and localhost development. Use a trusted network and keep dependencies updated.

Pentagon Island v0.8.3 - Multiplayer & Trade Update

Changes:
- Human players may forfeit an active match via Return to Menu confirmation.
- Forfeited players can return to the active match only as spectators.
- Host transfer is restricted to connected human players (never AI).
- On lobby reset, spectators are promoted to player slots when space permits.
- Public game logs hide opponents' exact resource gains. Own gains remain private.
- Spectators cannot inspect private inventories.
- Human trade proposals do not reveal the recipient's inventory.
- Pending human trades block End Turn on the server; the button stays clickable and shows a modal.
- 120-second server-enforced trade expiration; counteroffers keep original deadline.
- Recipient can accept, reject, or make one counteroffer.
- AI trades receive immediate accept/reject/counteroffer decisions; human 'TRADE SENT' notice dismisses after two seconds.
- AI difficulty remains locked after match start; sticky menu preserved.

Known limitations:
- WebRTC P2P is not implemented; FastAPI/WebSockets remain in use.
- Windows .exe is not precompiled; build-windows.bat produces it on Windows.
- Victory-to-lobby transition remains dependent on the existing game/session reset workflow.

Theme update: dark mode is the default for new users; saved light/dark preferences are preserved.

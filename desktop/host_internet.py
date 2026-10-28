"""Host an internet match; requires cloudflared on PATH. Run from project root."""
import re, shutil, subprocess, sys, threading, time
import uvicorn
from app.main import app

PORT = 8765

def main():
    exe = shutil.which('cloudflared')
    if not exe:
        raise SystemExit('Install cloudflared first: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=PORT, log_level='warning'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    tunnel = subprocess.Popen([exe,'tunnel','--url',f'http://127.0.0.1:{PORT}','--no-autoupdate'], stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    print('Starting temporary internet tunnel...')
    try:
        for line in tunnel.stdout:
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
            if match:
                print('\nHOST URL:',match.group(0),flush=True)
                print('Share this URL with browser players. They must also enter your game room code.\n',flush=True)
                break
            if tunnel.poll() is not None: raise RuntimeError('cloudflared exited before providing an invite URL')
        print('Local game:', f'http://127.0.0.1:{PORT}')
        print('Press Ctrl+C to end the host session.')
        while tunnel.poll() is None: time.sleep(.5)
    except KeyboardInterrupt: pass
    finally:
        tunnel.terminate();server.should_exit=True;thread.join(timeout=4)

if __name__=='__main__': main()

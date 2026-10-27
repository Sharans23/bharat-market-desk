"""Run real UI workflows against isolated, disposable local and hosted workspaces."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from werkzeug.serving import make_server, WSGIRequestHandler
from india_trader.cloud import create_app
from india_trader.web import Application, Server


class QuietHandler(WSGIRequestHandler):
    def log(self, *args, **kwargs): pass


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temp:
        hosted_key = secrets.token_urlsafe(32)
        local = Server(('127.0.0.1', 0), Application(Path(temp) / 'local'))
        # Reserve the port before supplying the strict configured origin.
        cloud = create_app(dict(TESTING=True, PUBLIC_ORIGIN='http://127.0.0.1', APP_DATA_DIR=str(Path(temp) / 'cloud'), APP_ACCESS_KEY=hosted_key, SESSION_SIGNING_KEY=secrets.token_urlsafe(32), CREDENTIAL_ENCRYPTION_KEY=secrets.token_urlsafe(32)))
        hosted = make_server('127.0.0.1', 0, cloud, threaded=True, request_handler=QuietHandler)
        origin = 'http://127.0.0.1:' + str(hosted.server_port)
        hosted.app = create_app(dict(TESTING=True, PUBLIC_ORIGIN=origin, APP_DATA_DIR=str(Path(temp) / 'cloud'), APP_ACCESS_KEY=hosted_key, SESSION_SIGNING_KEY=secrets.token_urlsafe(32), CREDENTIAL_ENCRYPTION_KEY=secrets.token_urlsafe(32)))
        for server in (local, hosted): threading.Thread(target=server.serve_forever, daemon=True).start()
        npm = 'npx.cmd' if os.name == 'nt' else 'npx'
        try:
            for spec, url in [('app.spec.js', 'http://127.0.0.1:' + str(local.server_port)), ('hosted.spec.js', origin)]:
                subprocess.run([npm, 'playwright', 'test', spec], cwd=root / 'ui', env={**os.environ, 'TEST_BASE_URL': url, 'TEST_ACCESS_KEY': hosted_key}, check=True)
        finally:
            # Local suite intentionally tests shutdown as its last action.
            hosted.shutdown(); hosted.server_close(); local.shutdown(); local.server_close()


if __name__ == '__main__': main()

#!/usr/bin/env python3
"""review.py — watch the edit, cut what is left, leave notes. Nothing else.

    python scripts/review.py edited.mp4

Opens a page in the browser: the video, what is said (sentence by sentence,
click to jump), the sound wave under it with every join of the edit. Two
things to do there:

  - CUT: select sentences (or drag on the wave) and press X. The cut is
    heard at once (playback jumps over it), nothing is rendered yet;
  - NOTE: press N and write what the edit should do there ("too long",
    "keep the first take"). Claude reads the notes and decides.

Everything is saved as you go into edited.edits.json. Then tell Claude
"apply my edits": it runs edit_video.py again with the same -o, which picks
the file up by itself (cuts applied, notes printed), re-transcribes nothing.

Standard library only; the page never leaves 127.0.0.1.
"""
import http.server, json, os, re, socketserver, sys, threading, webbrowser

if len(sys.argv) < 2 or not os.path.exists(sys.argv[1]):
    sys.exit('usage: python scripts/review.py edited.mp4   (run edit_video.py first)')
VIDEO = os.path.abspath(sys.argv[1])
BASE = os.path.splitext(VIDEO)[0]
TIMELINE, EDITS = f'{BASE}.timeline.json', f'{BASE}.edits.json'
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'review.html')
if not os.path.exists(TIMELINE):
    sys.exit(f'{os.path.basename(TIMELINE)} not found: run edit_video.py again, it writes it')


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/':
            self.send(200, open(PAGE, 'rb').read(), 'text/html; charset=utf-8')
        elif path == '/timeline.json':
            self.send(200, open(TIMELINE, 'rb').read(), 'application/json')
        elif path == '/edits.json':
            body = open(EDITS, 'rb').read() if os.path.exists(EDITS) else b'{"cuts": [], "notes": []}'
            self.send(200, body, 'application/json')
        elif path == '/video':
            self.video()
        else:
            self.send(404, b'not found', 'text/plain')

    def video(self):
        """Range requests: without them the browser cannot seek."""
        size = os.path.getsize(VIDEO)
        m = re.match(r'bytes=(\d*)-(\d*)', self.headers.get('Range', ''))
        a, b = 0, size - 1
        if m:
            if m.group(1):
                a = int(m.group(1))
                b = int(m.group(2)) if m.group(2) else size - 1
            else:
                a = size - int(m.group(2))
        b = min(b, size - 1)
        self.send_response(206 if m else 200)
        self.send_header('Content-Type', 'video/mp4')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(b - a + 1))
        if m:
            self.send_header('Content-Range', f'bytes {a}-{b}/{size}')
        self.end_headers()
        with open(VIDEO, 'rb') as f:
            f.seek(a)
            left = b - a + 1
            try:
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_POST(self):
        if self.path != '/edits.json':
            return self.send(404, b'not found', 'text/plain')
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        tmp = EDITS + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, EDITS)
        self.send(200, b'{"ok": true}', 'application/json')


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


srv = Server(('127.0.0.1', int(os.environ.get('REVIEW_PORT', 0))), Handler)
url = f'http://127.0.0.1:{srv.server_address[1]}/'
print(f'review page: {url}   (edits saved to {os.path.basename(EDITS)}; Ctrl+C to stop)', flush=True)
if not os.environ.get('REVIEW_NO_BROWSER'):
    threading.Timer(0.3, webbrowser.open, [url]).start()
try:
    srv.serve_forever()
except KeyboardInterrupt:
    pass

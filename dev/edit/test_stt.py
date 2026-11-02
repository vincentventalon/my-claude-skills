#!/usr/bin/env python3
"""test_stt.py — the ElevenLabs Scribe path, tested without paying and without
the network (for the maintainer, not part of the skill).

    python dev/edit/test_stt.py                       # the tests, ~2 s
    python dev/edit/test_stt.py --replay answer.json  # serve a recorded answer

The tests start a local server that plays the ElevenLabs speech-to-text
endpoint: it checks the request the skill sends (POST multipart, the
xi-api-key header, model_id, timestamps_granularity=word, language_code, a
FLAC file) and answers with dev/fixtures/scribe-answer.json, an answer made by
hand in the shape of the API documentation (words with start / end / type
word | spacing | audio_event, punctuation as its own entry, a made-up
zero-length word). They check that:
  - the answer becomes words in the contract of stt.py — (start, end, text),
    in order, punctuation glued, no spacing, no audio event, no zero-length word;
  - each word goes to the island it starts in (assign), the same shape the
    whisper path gives;
  - the second call of the same audio is read from the cache: no request;
  - no key, a refused key (401) and an empty quota (402) stop with what to do.

--replay serves any recorded answer the same way (until Ctrl-C), for an
end-to-end run of edit_video.py --stt elevenlabs on a real clip:
    VIDEO_EDITING_SCRIBE_URL=http://127.0.0.1:PORT/v1/speech-to-text \\
    ELEVENLABS_API_KEY=test python skills/edit/scripts/edit_video.py clip.mp4 --stt elevenlabs
(a cached answer is never asked again: delete ~/.cache/video-editing/elevenlabs/
to replay a new one for the same clip).
"""
import argparse, http.server, json, math, os, struct, sys, tempfile, threading, wave

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'skills', 'edit', 'scripts')
FIXTURE = os.path.join(HERE, 'fixtures', 'scribe-answer.json')
KEY = 'test-key-not-a-real-one'


class Endpoint(http.server.BaseHTTPRequestHandler):
    answer, status, seen = None, 200, []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        ctype = self.headers.get('Content-Type', '')
        fields, audio = {}, b''
        if 'boundary=' in ctype:
            bnd = ctype.split('boundary=')[1].encode()
            for part in body.split(b'--' + bnd)[1:-1]:
                head, _, data = part.strip(b'\r\n').partition(b'\r\n\r\n')
                name = head.split(b'name="')[1].split(b'"')[0].decode()
                if b'filename=' in head:
                    audio = data
                else:
                    fields[name] = data.decode()
        Endpoint.seen.append({'path': self.path, 'key': self.headers.get('xi-api-key'), 'ctype': ctype,
                              'fields': fields, 'audio': audio[:4], 'size': len(audio)})
        if Endpoint.status != 200:
            msg = {401: {'detail': {'status': 'invalid_api_key'}},
                   402: {'detail': {'status': 'quota_exceeded', 'message': 'This request exceeds your quota'}}}
            out, code = json.dumps(msg.get(Endpoint.status, {})).encode(), Endpoint.status
        else:
            out, code = json.dumps(Endpoint.answer).encode(), 200
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def serve(answer, port=0):
    Endpoint.answer = answer
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', port), Endpoint)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}/v1/speech-to-text'


def tone_wav(path, seconds=6.0, sr=16000):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(b''.join(struct.pack('<h', int(8000 * math.sin(2 * math.pi * 220 * n / sr)))
                               for n in range(int(seconds * sr))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--replay', help='serve this recorded answer until Ctrl-C')
    ap.add_argument('--port', type=int, default=0)
    a = ap.parse_args()
    if a.replay:
        srv, url = serve(json.load(open(a.replay, encoding='utf-8')), a.port)
        print(f'replaying {a.replay} at {url}\n  VIDEO_EDITING_SCRIBE_URL={url} ELEVENLABS_API_KEY=test ...')
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            srv.shutdown()
        return

    fixture = json.load(open(FIXTURE, encoding='utf-8'))
    srv, url = serve(fixture)
    os.environ['VIDEO_EDITING_SCRIBE_URL'] = url
    os.environ['ELEVENLABS_API_KEY'] = KEY
    sys.path.insert(0, SCRIPTS)
    import settings, stt                                    # noqa: E402  (after the URL is set)
    tmp = tempfile.mkdtemp(prefix='stt-test-')
    stt.SCRIBE_CACHE = os.path.join(tmp, 'cache')
    ff = settings.find_ffmpeg()
    wav = os.path.join(tmp, 'a.wav')
    tone_wav(wav)
    fails = []

    def check(name, ok, detail=''):
        print(('PASS ' if ok else 'FAIL ') + name + (f'  ({detail})' if detail and not ok else ''))
        if not ok:
            fails.append(name)

    words = stt.scribe(wav, 'fr', ff)
    req = Endpoint.seen[-1] if Endpoint.seen else {}
    f = req.get('fields', {})
    check('one POST to the speech-to-text endpoint', len(Endpoint.seen) == 1 and req['path'] == '/v1/speech-to-text')
    check('the key goes in xi-api-key', req.get('key') == KEY)
    check('multipart/form-data', req.get('ctype', '').startswith('multipart/form-data; boundary='))
    check(f'model_id = {stt.SCRIBE_MODEL}', f.get('model_id') == stt.SCRIBE_MODEL, f)
    check('timestamps_granularity = word', f.get('timestamps_granularity') == 'word', f)
    check('language_code = fr', f.get('language_code') == 'fr', f)
    check('no audio events, no diarization', f.get('tag_audio_events') == 'false' and f.get('diarize') == 'false', f)
    check('the audio goes as FLAC', req.get('audio') == b'fLaC' and req.get('size', 0) > 1000, req.get('audio'))

    expect = [(0.12, 0.6, 'Bonjour,'), (0.9, 1.0, 'je'), (1.02, 1.2, 'vais'), (1.22, 1.45, 'vous'),
              (1.5, 1.7, 'mon--'), (2.4, 2.5, 'je'), (2.52, 2.7, 'vais'), (2.72, 2.9, 'vous'),
              (2.92, 3.3, 'montrer'), (3.32, 3.7, 'comment'), (3.72, 4.2, 'couper.')]
    check('the contract: (start, end, text), punctuation glued, no spacing / event / zero-length word',
          words == expect, words)
    check('in order, start <= end', all(s <= e for s, e, _t in words)
          and all(words[k][0] <= words[k + 1][0] for k in range(len(words) - 1)))

    spans = [(0.1, 1.72), (2.38, 4.25), (4.3, 5.1)]
    got = stt.assign(words, spans)
    check('each word to the island it starts in', [' '.join(t for *_x, t in g) for g in got]
          == ['Bonjour, je vais vous mon--', 'je vais vous montrer comment couper.', ''], got)
    check('every word inside its island', all(a <= s <= e <= b for (a, b), g in zip(spans, got) for s, e, _t in g))
    early = stt.assign([(2.2, 2.3, 'et')], spans)
    check('a soft attack just before an island belongs to it', early[1] == [(2.38, 2.38, 'et')], early)
    check('a word in a silence the cut removes belongs to no island',
          stt.assign([(1.9, 2.0, 'heu')], spans) == [[], [], []])

    again = stt.scribe(wav, 'fr', ff)
    check('the same audio again: read from the cache, no request', again == words and len(Endpoint.seen) == 1)

    tone_wav(wav, 5.0)                                      # another audio: not in the cache
    for code, word in ((401, 'refused the key'), (402, 'no credits')):
        Endpoint.status = code
        try:
            stt.scribe(wav, 'fr', ff)
            check(f'{code} stops', False, 'did not stop')
        except SystemExit as e:
            check(f'{code} stops with what to do', word in str(e) and KEY not in str(e), str(e))
    Endpoint.status = 200
    del os.environ['ELEVENLABS_API_KEY']
    try:
        stt.scribe(wav, 'fr', ff)
        check('no key stops', False, 'did not stop')
    except SystemExit as e:
        check('no key stops before any request', 'ELEVENLABS_API_KEY' in str(e) and len(Endpoint.seen) == 3, str(e))

    srv.shutdown()
    print(f'\n{len(fails)} failure(s)' if fails else '\nall green: nothing paid, nothing sent outside this computer')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()

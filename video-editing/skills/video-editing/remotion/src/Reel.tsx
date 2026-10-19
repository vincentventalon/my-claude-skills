import {
  AbsoluteFill, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';

type Island = { start: number; end: number; text: string };
type Timeline = { width: number; height: number; duration: number; islands: Island[] };

export type ReelProps = {
  title: string;                        // big line on top ('' = none)
  layout: 'auto' | 'full' | 'frame';    // auto: filmed upright = full screen, filmed sideways = framed
  captions: boolean;
  timeline?: Timeline;                  // filled in by Root from public/timeline.json
};

const LIME = '#e9f76a';
const GREEN = '#5fe3a1';
const FONT = 'Inter, "SF Pro Display", "Segoe UI", system-ui, sans-serif';

// ---- captions: a few words at a time, the word being said lights up -----------
// The transcript is timed per sentence, not per word: each word gets a share of
// the sentence's time in proportion to its length. Close enough to read along.
type Word = { w: string; a: number; b: number };
type Line = { words: Word[]; a: number; b: number };

function lines(islands: Island[], max = 4): Line[] {
  const out: Line[] = [];
  for (const s of islands) {
    const ws = s.text.split(/\s+/).filter(Boolean);
    if (!ws.length) continue;
    const total = ws.reduce((n, w) => n + w.length + 1, 0);
    let t = s.start;
    const timed = ws.map((w) => {
      const d = ((s.end - s.start) * (w.length + 1)) / total;
      const x = { w, a: t, b: t + d };
      t += d;
      return x;
    });
    for (let i = 0; i < timed.length; i += max) {
      const words = timed.slice(i, i + max);
      out.push({ words, a: words[0].a, b: words[words.length - 1].b });
    }
  }
  return out;
}

const Captions: React.FC<{ tl: Timeline; y: string; size: number }> = ({ tl, y, size }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const line = lines(tl.islands).find((l) => t >= l.a && t < l.b + 0.15);
  if (!line) return null;
  const pop = spring({ frame: frame - Math.round(line.a * fps), fps, config: { damping: 14, stiffness: 180 } });
  return (
    <AbsoluteFill style={{ top: y, height: 'auto', alignItems: 'center', padding: '0 70px' }}>
      <div style={{
        fontFamily: FONT, fontWeight: 900, fontSize: size, lineHeight: 1.1, textAlign: 'center',
        color: 'white', textTransform: 'uppercase', letterSpacing: '-0.01em',
        transform: `scale(${interpolate(pop, [0, 1], [0.85, 1])})`,
        textShadow: '0 6px 24px rgba(0,0,0,.55), 0 0 2px rgba(0,0,0,.9)',
        WebkitTextStroke: '2px rgba(0,0,0,.35)',
      }}>
        {line.words.map((w, i) => (
          <span key={i} style={{ color: t >= w.a && t < w.b ? LIME : 'white' }}>{w.w} </span>
        ))}
      </div>
    </AbsoluteFill>
  );
};

const Title: React.FC<{ text: string; top: number }> = ({ text, top }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!text) return null;
  const s = spring({ frame, fps, config: { damping: 16 } });
  return (
    <AbsoluteFill style={{ top, height: 'auto', alignItems: 'center', padding: '0 80px' }}>
      <div style={{
        fontFamily: FONT, fontWeight: 900, fontSize: 76, lineHeight: 1.05, textAlign: 'center', color: 'white',
        opacity: s, transform: `translateY(${interpolate(s, [0, 1], [-40, 0])}px)`,
        textShadow: '0 6px 30px rgba(0,0,0,.5)',
      }}>
        {text.split(/(\*[^*]+\*)/).map((p, i) => p.startsWith('*')
          ? <span key={i} style={{ background: `linear-gradient(90deg, ${LIME}, ${GREEN})`,
              WebkitBackgroundClip: 'text', color: 'transparent' }}>{p.slice(1, -1)}</span>
          : <span key={i}>{p}</span>)}
      </div>
    </AbsoluteFill>
  );
};

// ---- the two layouts ------------------------------------------------------------
const Full: React.FC<{ p: ReelProps; tl: Timeline }> = ({ p, tl }) => (
  <AbsoluteFill style={{ backgroundColor: 'black' }}>
    <OffthreadVideo src={staticFile('video.mp4')} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
    <AbsoluteFill style={{ background: 'linear-gradient(180deg, rgba(0,0,0,.45) 0%, transparent 22%, transparent 55%, rgba(0,0,0,.35) 100%)' }} />
    <Title text={p.title} top={150} />
    {p.captions && <Captions tl={tl} y="64%" size={78} />}
  </AbsoluteFill>
);

const Framed: React.FC<{ p: ReelProps; tl: Timeline }> = ({ p, tl }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const k = Math.min(960 / tl.width, 1080 / tl.height);          // the card fits in 960 x 1080
  const w = tl.width * k, h = tl.height * k;
  const s = spring({ frame, fps, config: { damping: 18 } });
  const drift = interpolate(frame, [0, durationInFrames], [0, 1]);
  return (
    <AbsoluteFill style={{ backgroundColor: '#0a0c0f', overflow: 'hidden' }}>
      {/* slow light behind the card */}
      <div style={{ position: 'absolute', width: 1400, height: 1400, borderRadius: '50%', filter: 'blur(160px)',
        left: -500 + 300 * drift, top: 200, background: GREEN, opacity: 0.22 }} />
      <div style={{ position: 'absolute', width: 1200, height: 1200, borderRadius: '50%', filter: 'blur(160px)',
        right: -500 + 250 * drift, bottom: -200, background: LIME, opacity: 0.16 }} />
      <Title text={p.title} top={170} />
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div style={{
          width: w, height: h, borderRadius: 40, overflow: 'hidden',
          boxShadow: '0 40px 120px rgba(0,0,0,.6), 0 0 0 2px rgba(255,255,255,.08)',
          transform: `scale(${interpolate(s, [0, 1], [0.9, 1])})`, opacity: s,
        }}>
          <OffthreadVideo src={staticFile('video.mp4')} style={{ width: '100%', height: '100%' }} />
        </div>
      </AbsoluteFill>
      {p.captions && <Captions tl={tl} y={`${(960 + h / 2 + 70) / 19.2}%`} size={64} />}
    </AbsoluteFill>
  );
};

export const Reel: React.FC<ReelProps> = (p) => {
  const tl = p.timeline;
  if (!tl) return null;
  const upright = tl.height > tl.width;
  const layout = p.layout === 'auto' ? (upright ? 'full' : 'frame') : p.layout;
  return layout === 'full' ? <Full p={p} tl={tl} /> : <Framed p={p} tl={tl} />;
};

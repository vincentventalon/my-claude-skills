import { useEffect, useState } from 'react';
import {
  AbsoluteFill, continueRender, delayRender, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';

// Everything drawn over the video except the subtitles, on a transparent background, for the whole
// length of the video: the title, the end card and, in the split view, the boards and the title kept
// at the top. scripts/finish.py decides what shows when and where (items, in seconds and px), renders
// this composition once to a ProRes 4444 clip and lays it over the video; the subtitles stay in the
// .ass. Every colour and size comes from style.json.
export type Item = {
  kind: 'title' | 'end' | 'header' | 'board';
  board?: 'text' | 'stat' | 'list';
  start: number;           // s
  end: number;             // s
  text: string;            // *word* = highlighted, ' | ' = new line (list: one item per part; stat: the figure | its caption)
  y: number;               // px, centre of the block
  size: number;            // px
  color: string;
  box: string;             // '' = no box (the split's top zone is the background)
  highlight: string;
  muted: string;           // the caption of a stat
  uppercase: boolean;
};

export type OverlayProps = {
  font: string;            // family name
  fontFile: string;        // file in public/fonts/ ('' = a font installed on the computer)
  width: number;
  height: number;
  fps: number;
  seconds: number;
  items: Item[];
};

export const defaultOverlay: OverlayProps = {
  font: 'Inter ExtraBold', fontFile: 'Inter-ExtraBold.ttf', width: 1080, height: 1920, fps: 30, seconds: 9,
  items: [
    { kind: 'title', start: 0, end: 3, text: 'My *big* idea', y: 326, size: 92, color: '#101114', box: '#FFFFFF',
      highlight: '#0F9D6B', muted: '#9AA1AD', uppercase: false },
    { kind: 'board', board: 'stat', start: 3, end: 6, text: '150 min | = 3 h of work', y: 430, size: 96,
      color: '#F3F4F6', box: '', highlight: '#3DDC97', muted: '#9AA1AD', uppercase: false },
    { kind: 'board', board: 'list', start: 6, end: 9, text: 'Cut | Subtitles | Publish', y: 430, size: 96,
      color: '#F3F4F6', box: '', highlight: '#3DDC97', muted: '#9AA1AD', uppercase: false },
  ],
};

function useFont(family: string, file: string) {
  const [handle] = useState(() => (file ? delayRender(`font ${file}`) : null));
  useEffect(() => {
    if (!file || handle === null) return;
    new FontFace(family, `url(${staticFile(`fonts/${file}`)})`).load()
      .then((f) => { document.fonts.add(f); continueRender(handle); })
      .catch(() => continueRender(handle));        // a missing font: the default one, not a failed render
  }, [family, file, handle]);
}

// *word* -> the highlight colour
const Styled: React.FC<{ text: string; highlight: string }> = ({ text, highlight }) => (
  <>
    {text.split(/(\*[^*]+\*)/).map((part, j) => part.startsWith('*') && part.endsWith('*') && part.length > 2
      ? <span key={j} style={{ color: highlight }}>{part.slice(1, -1)}</span>
      : <span key={j}>{part}</span>)}
  </>
);

// a figure that counts up to its value when it starts with a number ("150 min", "3,5 h", "x10")
const CountUp: React.FC<{ text: string; progress: number }> = ({ text, progress }) => {
  const m = text.match(/^([^0-9]*)(\d+(?:[.,]\d+)?)(.*)$/);
  if (!m) return <>{text}</>;
  const [, pre, num, post] = m;
  const decimals = (num.split(/[.,]/)[1] || '').length;
  const value = parseFloat(num.replace(',', '.')) * progress;
  const shown = value.toFixed(decimals).replace('.', num.includes(',') ? ',' : '.');
  return <>{pre}{shown}{post}</>;
};

const Block: React.FC<{ it: Item; font: string; width: number; fps: number }> = ({ it, font, width, fps }) => {
  const frame = useCurrentFrame();
  const local = frame - it.start * fps;
  const len = (it.end - it.start) * fps;
  if (local < 0 || local >= len) return null;
  const end = it.kind === 'end';
  const s = spring({ frame: local, fps, config: end ? { damping: 10, stiffness: 170 } : { damping: 16, stiffness: 140 } });
  const scale = interpolate(s, [0, 1], [end ? 0.6 : 0.92, 1]);
  const lift = end ? 0 : interpolate(s, [0, 1], [24, 0]);
  const fadeOut = end ? 1 : interpolate(local, [len - 0.22 * fps, len], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  // French spacing: the space before : ; ! ? never breaks the line
  const text = (it.uppercase ? it.text.toUpperCase() : it.text).replace(/ ([:;!?»])/g, '\u00a0$1').replace(/« /g, '«\u00a0');
  const parts = text.split(/\s*\|\s*/).filter(Boolean);
  const family = `"${font}", "Inter", "Helvetica Neue", Arial, system-ui, sans-serif`;
  const pad = Math.round(width * 0.07);

  let body: React.ReactNode;
  if (it.kind === 'board' && it.board === 'stat') {
    const count = interpolate(local, [0, 0.7 * fps], [0, 1], { extrapolateRight: 'clamp', easing: (t) => 1 - Math.pow(1 - t, 3) });
    body = (
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: it.size * 1.9, lineHeight: 1.0, color: it.highlight, letterSpacing: '-0.02em' }}>
          <CountUp text={parts[0] || ''} progress={count} />
        </div>
        {parts.slice(1).map((p, i) => (
          <div key={i} style={{ fontSize: it.size * 0.62, lineHeight: 1.25, color: it.muted, marginTop: it.size * 0.22 }}>
            <Styled text={p} highlight={it.highlight} />
          </div>
        ))}
      </div>
    );
  } else if (it.kind === 'board' && it.board === 'list') {
    const step = Math.min(0.35, (it.end - it.start) / Math.max(parts.length, 1) / 2) * fps;
    body = (
      <div style={{ display: 'flex', flexDirection: 'column', gap: it.size * 0.34, alignItems: 'flex-start' }}>
        {parts.map((p, i) => {
          const r = spring({ frame: local - i * step, fps, config: { damping: 16, stiffness: 150 } });
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: it.size * 0.36, opacity: r,
              transform: `translateX(${interpolate(r, [0, 1], [-30, 0])}px)`, fontSize: it.size * 0.78, lineHeight: 1.1 }}>
              <span style={{ color: it.highlight, minWidth: it.size * 0.6 }}>{i + 1}</span>
              <span style={{ color: it.color }}><Styled text={p} highlight={it.highlight} /></span>
            </div>
          );
        })}
      </div>
    );
  } else {
    // title, header, end card, a text board: lines, with or without a box behind each
    body = (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: Math.round(it.size * 0.1) }}>
        {parts.map((line, i) => (
          <div key={i} style={{ textAlign: 'center', lineHeight: 1.18, textWrap: 'balance' }}>
            <span style={it.box ? {
              background: it.box, padding: `${Math.round(it.size * 0.1)}px ${Math.round(it.size * 0.32)}px`,
              borderRadius: Math.round(it.size * 0.24), boxDecorationBreak: 'clone', WebkitBoxDecorationBreak: 'clone',
              boxShadow: '0 12px 32px rgba(0,0,0,.25)',
            } : {}}>
              <Styled text={line} highlight={it.highlight} />
            </span>
          </div>
        ))}
      </div>
    );
  }

  if (it.box && it.kind === 'board' && it.board !== 'text') {
    // over the camera (full frame): the figure or the list on a card
    body = (
      <div style={{ background: it.box, borderRadius: Math.round(it.size * 0.3), padding: `${Math.round(it.size * 0.36)}px ${Math.round(it.size * 0.5)}px`,
        boxShadow: '0 12px 32px rgba(0,0,0,.25)' }}>{body}</div>
    );
  }

  return (
    <div style={{
      position: 'absolute', left: pad, right: pad, top: it.y, display: 'flex', justifyContent: 'center',
      transform: `translateY(-50%) translateY(${lift}px) scale(${scale})`, opacity: Math.min(s * 1.6, 1) * fadeOut,
      fontFamily: family, fontSize: it.size, color: it.color, letterSpacing: '-0.01em',
    }}>
      {body}
    </div>
  );
};

export const Overlay: React.FC<OverlayProps> = (p) => {
  useFont(p.font, p.fontFile);
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      {p.items.map((it, i) => <Block key={i} it={it} font={p.font} width={p.width} fps={fps} />)}
    </AbsoluteFill>
  );
};

import { useEffect, useState } from 'react';
import {
  AbsoluteFill, continueRender, delayRender, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';

// One card on a transparent background: the title (first seconds) or the end
// card (last seconds). scripts/finish.py renders it to a ProRes 4444 clip and
// lays it over the video; the subtitles stay in the .ass. Every prop comes from
// style.json (finish.py writes them in a props file).
export type CardProps = {
  kind: 'title' | 'end';
  text: string;            // *word* = highlighted, ' | ' = new line
  font: string;            // family name
  fontFile: string;        // file in public/fonts/ ('' = a font installed on the computer)
  size: number;            // px
  color: string;           // text
  box: string;             // the box behind each line
  highlight: string;       // *word*
  uppercase: boolean;
  y: number;               // centre of the card, 0 = top, 1 = bottom
  width: number;
  height: number;
  fps: number;
  seconds: number;
};

export const defaultCard: CardProps = {
  kind: 'title', text: 'My *big* idea', font: 'Anton', fontFile: 'Anton-Regular.ttf', size: 82,
  color: '#111111', box: '#FFFFFF', highlight: '#E5322D', uppercase: false, y: 0.17,
  width: 1080, height: 1920, fps: 30, seconds: 3.5,
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

export const Card: React.FC<CardProps> = (p) => {
  useFont(p.font, p.fontFile);
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const t = p.uppercase ? p.text.toUpperCase() : p.text;
  const lines = t.split(/\s*\|\s*/);

  // in: a spring (the end card overshoots a little, the title does not); out: the title fades
  const s = spring({ frame, fps, config: p.kind === 'end' ? { damping: 9, stiffness: 160 } : { damping: 18 } });
  const scale = interpolate(s, [0, 1], [p.kind === 'end' ? 0.55 : 0.9, 1]);
  const lift = p.kind === 'title' ? interpolate(s, [0, 1], [-30, 0]) : 0;
  const out = p.kind === 'title'
    ? interpolate(frame, [durationInFrames - 0.3 * fps, durationInFrames], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
    : 1;

  return (
    <AbsoluteFill>
      <div style={{
        position: 'absolute', left: 0, right: 0, top: p.y * p.height, transform: `translateY(-50%) translateY(${lift}px) scale(${scale})`,
        opacity: Math.min(s * 1.6, 1) * out, display: 'flex', flexDirection: 'column', alignItems: 'center',
        padding: `0 ${Math.round(p.width * 0.04)}px`, gap: Math.round(p.size * 0.12),
      }}>
        {lines.map((line, i) => (
          <div key={i} style={{ textAlign: 'center', lineHeight: 1.32, textWrap: 'balance' }}>
            <span style={{
              fontFamily: `"${p.font}", "Arial Black", system-ui, sans-serif`, fontSize: p.size, color: p.color,
              background: p.box, padding: `${Math.round(p.size * 0.08)}px ${Math.round(p.size * 0.3)}px`,
              borderRadius: Math.round(p.size * 0.26), boxDecorationBreak: 'clone', WebkitBoxDecorationBreak: 'clone',
              boxShadow: '0 10px 30px rgba(0,0,0,.28)',
            }}>
              {line.split(/(\*[^*]+\*)/).map((part, j) => part.startsWith('*') && part.endsWith('*') && part.length > 2
                ? <span key={j} style={{ color: p.highlight }}>{part.slice(1, -1)}</span>
                : <span key={j}>{part}</span>)}
            </span>
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

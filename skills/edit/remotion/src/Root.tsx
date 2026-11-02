import { Composition } from 'remotion';
import { Card, defaultCard, type CardProps } from './Card';

// scripts/finish.py renders this composition twice per video (the title, the
// end card) with --props=<file>, on a transparent background:
//   npx remotion render src/index.ts Card out.mov --props=props.json --codec=prores
//     --prores-profile=4444 --pixel-format=yuva444p10le --image-format=png
// `npm run studio` shows it with the default props.
export const Root = () => (
  <Composition
    id="Card"
    component={Card}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={105}
    defaultProps={defaultCard as CardProps}
    calculateMetadata={async ({ props }) => ({
      width: props.width,
      height: props.height,
      fps: props.fps,
      durationInFrames: Math.max(1, Math.round(props.seconds * props.fps)),
    })}
  />
);

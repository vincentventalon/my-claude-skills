import { Composition } from 'remotion';
import { Overlay, defaultOverlay, type OverlayProps } from './Overlay';

// scripts/finish.py renders this composition once, the whole length of the video, with --props=<file>, on a transparent background:
//   npx remotion render src/index.ts Overlay out.mov --props=props.json --codec=prores
//     --prores-profile=4444 --pixel-format=yuva444p10le --image-format=png
// `npm run studio` shows it with the default props.
export const Root = () => (
  <Composition
    id="Overlay"
    component={Overlay}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={270}
    defaultProps={defaultOverlay as OverlayProps}
    calculateMetadata={async ({ props }) => ({
      width: props.width,
      height: props.height,
      fps: props.fps,
      durationInFrames: Math.max(1, Math.round(props.seconds * props.fps)),
    })}
  />
);

import { Composition, staticFile } from 'remotion';
import { Reel, type ReelProps } from './Reel';

// public/video.mp4 + public/timeline.json = edited.mp4 + edited.timeline.json,
// copied as they come out of scripts/edit_video.py.
export const Root = () => (
  <Composition
    id="Reel"
    component={Reel}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={300}
    defaultProps={{ title: '', layout: 'auto', captions: true } as ReelProps}
    calculateMetadata={async ({ props }) => {
      const t = await fetch(staticFile('timeline.json')).then((r) => r.json());
      return {
        durationInFrames: Math.max(1, Math.ceil(t.duration * 30)),
        props: { ...props, timeline: t },
      };
    }}
  />
);

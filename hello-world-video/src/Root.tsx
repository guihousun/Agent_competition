import {Composition} from 'remotion';
import {HelloWorld} from './HelloWorld';
import {COMPOSITION} from './timing';

export const RemotionRoot = () => {
  return (
    <Composition
      id="HelloWorld"
      component={HelloWorld}
      durationInFrames={COMPOSITION.durationInFrames}
      fps={COMPOSITION.fps}
      width={COMPOSITION.width}
      height={COMPOSITION.height}
    />
  );
};

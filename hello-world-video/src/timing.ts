import {Easing, interpolate} from 'remotion';

export const COMPOSITION = {
  fps: 30,
  durationInFrames: 120,
  width: 1920,
  height: 1080,
} as const;

export const getExitOpacity = (frame: number): number => {
  return interpolate(frame, [104, 119], [1, 0], {
    easing: Easing.in(Easing.cubic),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
};

export const getSceneScale = (frame: number): number => {
  const entranceScale = interpolate(frame, [0, 30], [0.92, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const exitScale = interpolate(frame, [104, 119], [1, 0.88], {
    easing: Easing.in(Easing.cubic),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return entranceScale * exitScale;
};

export const getAccentProgress = (
  frame: number,
  delayInFrames: number,
): number => {
  return interpolate(
    frame,
    [delayInFrames, delayInFrames + 18],
    [0, 1],
    {
      easing: Easing.bezier(0.34, 1.56, 0.64, 1),
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );
};

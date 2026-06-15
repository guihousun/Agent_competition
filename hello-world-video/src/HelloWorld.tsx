import type {CSSProperties} from 'react';
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {
  getAccentProgress,
  getExitOpacity,
  getSceneScale,
} from './timing';

type AccentProps = {
  color: string;
  delay: number;
  height: number;
  left: number;
  rotation: number;
  shape: 'circle' | 'diamond' | 'pill' | 'triangle';
  top: number;
  width: number;
};

const accentBase: CSSProperties = {
  position: 'absolute',
  border: '8px solid #151515',
  boxSizing: 'border-box',
};

const Accent = ({
  color,
  delay,
  height,
  left,
  rotation,
  shape,
  top,
  width,
}: AccentProps) => {
  const frame = useCurrentFrame();
  const progress = getAccentProgress(frame, delay);
  const floatOffset = Math.sin((frame - delay) / 13) * 8 * progress;

  const shapeStyle: CSSProperties =
    shape === 'circle'
      ? {borderRadius: '50%'}
      : shape === 'pill'
        ? {borderRadius: 999}
        : shape === 'triangle'
          ? {
              clipPath: 'polygon(50% 0%, 100% 100%, 0% 100%)',
              border: 'none',
              filter:
                'drop-shadow(6px 0 0 #151515) drop-shadow(-6px 0 0 #151515) drop-shadow(0 7px 0 #151515)',
            }
          : {borderRadius: 8};

  return (
    <div
      style={{
        ...accentBase,
        ...shapeStyle,
        backgroundColor: color,
        height,
        left,
        opacity: progress,
        top,
        transform: `translateY(${interpolate(progress, [0, 1], [90, 0]) + floatOffset}px) rotate(${rotation * progress}deg) scale(${interpolate(progress, [0, 1], [0.25, 1])})`,
        width,
      }}
    />
  );
};

const accents: AccentProps[] = [
  {
    color: '#ffffff',
    delay: 5,
    height: 116,
    left: 210,
    rotation: -18,
    shape: 'diamond',
    top: 190,
    width: 116,
  },
  {
    color: '#ff4f7b',
    delay: 9,
    height: 72,
    left: 1460,
    rotation: 25,
    shape: 'circle',
    top: 175,
    width: 72,
  },
  {
    color: '#151515',
    delay: 13,
    height: 52,
    left: 250,
    rotation: 16,
    shape: 'pill',
    top: 760,
    width: 210,
  },
  {
    color: '#ffffff',
    delay: 17,
    height: 130,
    left: 1520,
    rotation: 13,
    shape: 'triangle',
    top: 710,
    width: 145,
  },
  {
    color: '#ff4f7b',
    delay: 21,
    height: 54,
    left: 1325,
    rotation: -10,
    shape: 'pill',
    top: 855,
    width: 185,
  },
];

export const HelloWorld = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const titleProgress = spring({
    frame,
    fps,
    config: {
      damping: 11,
      mass: 0.72,
      stiffness: 135,
    },
    durationInFrames: 42,
  });
  const titleScale = interpolate(titleProgress, [0, 1], [0.25, 1]);
  const titleRotation = interpolate(titleProgress, [0, 1], [-10, -2.5]);
  const sceneOpacity = getExitOpacity(frame);
  const sceneScale = getSceneScale(frame);
  const stripeShift = interpolate(frame, [0, 119], [-80, 80], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#f6e64d',
        color: '#ffffff',
        fontFamily:
          '"Arial Black", "Segoe UI Black", "Helvetica Neue", sans-serif',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: -120,
          opacity: 0.12,
          transform: `translateX(${stripeShift}px) rotate(-12deg)`,
          backgroundImage:
            'repeating-linear-gradient(90deg, #151515 0, #151515 10px, transparent 10px, transparent 68px)',
        }}
      />

      <div
        style={{
          position: 'absolute',
          inset: 0,
          opacity: sceneOpacity,
          transform: `scale(${sceneScale})`,
        }}
      >
        {accents.map((accent, index) => (
          <Accent key={`${accent.shape}-${index}`} {...accent} />
        ))}

        <div
          style={{
            left: '50%',
            position: 'absolute',
            top: '50%',
            transform: `translate(-50%, -50%) rotate(${titleRotation}deg) scale(${titleScale})`,
          }}
        >
          <div
            style={{
              backgroundColor: '#151515',
              height: 350,
              left: 32,
              position: 'absolute',
              top: 32,
              width: 1240,
            }}
          />
          <div
            style={{
              alignItems: 'center',
              backgroundColor: '#ff4f7b',
              border: '14px solid #151515',
              boxSizing: 'border-box',
              display: 'flex',
              height: 350,
              justifyContent: 'center',
              padding: '35px 60px',
              position: 'relative',
              width: 1240,
            }}
          >
            <div
              style={{
                fontSize: 132,
                fontWeight: 950,
                letterSpacing: -6,
                lineHeight: 0.92,
                textAlign: 'center',
                textShadow: '7px 7px 0 rgba(21, 21, 21, 0.16)',
                whiteSpace: 'nowrap',
              }}
            >
              HELLO WORLD!
            </div>
          </div>
        </div>

        <div
          style={{
            bottom: 54,
            color: '#151515',
            fontFamily: '"Courier New", monospace',
            fontSize: 25,
            fontWeight: 800,
            left: 0,
            letterSpacing: 8,
            position: 'absolute',
            right: 0,
            textAlign: 'center',
          }}
        >
          MADE WITH REMOTION
        </div>
      </div>
    </AbsoluteFill>
  );
};

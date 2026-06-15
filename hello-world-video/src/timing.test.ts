import {describe, expect, it} from 'vitest';
import {
  COMPOSITION,
  getAccentProgress,
  getExitOpacity,
  getSceneScale,
} from './timing';

describe('hello world timing', () => {
  it('uses a four-second 30 fps composition', () => {
    expect(COMPOSITION.durationInFrames).toBe(120);
    expect(COMPOSITION.fps).toBe(30);
  });

  it('holds full opacity until the exit and fades by the final frame', () => {
    expect(getExitOpacity(0)).toBe(1);
    expect(getExitOpacity(90)).toBe(1);
    expect(getExitOpacity(119)).toBeLessThan(0.1);
  });

  it('grows the scene during the entrance', () => {
    expect(getSceneScale(0)).toBeLessThan(getSceneScale(30));
  });

  it('honors accent delays and clamps progress', () => {
    expect(getAccentProgress(0, 8)).toBe(0);
    expect(getAccentProgress(30, 8)).toBe(1);
  });
});

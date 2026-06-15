# Hello World Remotion Video Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and render a four-second 1920 x 1080 pop-art "HELLO WORLD!" video with Remotion.

**Architecture:** Keep the TypeScript/React video project in `hello-world-video/`, isolated from the repository's Python runtime. Export composition constants and pure timing helpers for unit tests, then use those helpers in one focused Remotion scene component.

**Tech Stack:** Remotion, React, TypeScript, Vitest, Node.js, npm

---

## File Structure

- `hello-world-video/package.json`: scripts and pinned project dependencies.
- `hello-world-video/tsconfig.json`: TypeScript compiler configuration.
- `hello-world-video/src/index.ts`: registers the Remotion root.
- `hello-world-video/src/Root.tsx`: declares the `HelloWorld` composition.
- `hello-world-video/src/timing.ts`: composition constants and pure timing helpers.
- `hello-world-video/src/timing.test.ts`: unit tests for timing behavior.
- `hello-world-video/src/HelloWorld.tsx`: pop-art scene and frame-driven motion.
- `hello-world-video/out/hello-world.mp4`: final rendered video.

### Task 1: Scaffold the Isolated Remotion Project

**Files:**
- Create: `hello-world-video/package.json`
- Create: `hello-world-video/tsconfig.json`
- Create: `hello-world-video/src/index.ts`
- Create: `hello-world-video/src/Root.tsx`

- [ ] **Step 1: Create the package manifest**

Use scripts for tests, type checking, still rendering, and MP4 rendering. Pin
compatible versions of `remotion`, `@remotion/cli`, `react`, `react-dom`,
`typescript`, and `vitest`.

- [ ] **Step 2: Install dependencies**

Run:

```powershell
npm install
```

Expected: exit code 0 and a generated `package-lock.json`.

- [ ] **Step 3: Add the Remotion entrypoint and composition declaration**

Register `RemotionRoot` from `src/index.ts`. Declare `HelloWorld` in
`src/Root.tsx` using imported constants for width, height, fps, and duration.

- [ ] **Step 4: Verify the project can resolve the Remotion CLI**

Run:

```powershell
npx remotion compositions src/index.ts
```

Expected: the `HelloWorld` composition is listed.

### Task 2: Define Timing Behavior with TDD

**Files:**
- Create: `hello-world-video/src/timing.test.ts`
- Create: `hello-world-video/src/timing.ts`

- [ ] **Step 1: Write failing timing tests**

Test these exact behaviors:

```ts
expect(COMPOSITION.durationInFrames).toBe(120);
expect(getExitOpacity(0)).toBe(1);
expect(getExitOpacity(119)).toBeLessThan(0.1);
expect(getSceneScale(0)).toBeLessThan(getSceneScale(30));
expect(getAccentProgress(0, 8)).toBe(0);
expect(getAccentProgress(30, 8)).toBe(1);
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
npm test
```

Expected: FAIL because `src/timing.ts` does not exist.

- [ ] **Step 3: Implement the minimum timing module**

Export:

```ts
export const COMPOSITION = {
  fps: 30,
  durationInFrames: 120,
  width: 1920,
  height: 1080,
} as const;
```

Implement `getExitOpacity`, `getSceneScale`, and `getAccentProgress` with
Remotion `interpolate()` calls and explicit clamping.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
npm test
```

Expected: all timing tests pass.

### Task 3: Implement the Pop-Art Scene

**Files:**
- Create: `hello-world-video/src/HelloWorld.tsx`
- Modify: `hello-world-video/src/Root.tsx`

- [ ] **Step 1: Build the frame-driven title animation**

Use `useCurrentFrame()` and `useVideoConfig()`. Animate title scale and rotation
with a Remotion `spring()` and apply final-scene opacity/scale from `timing.ts`.

- [ ] **Step 2: Add the visual hierarchy**

Render:

```text
yellow background
black hard-shadow panel
pink bordered title panel
white HELLO WORLD! title
black, white, and pink geometric accents
```

Keep the title within the 1920 x 1080 safe area at all tested frames.

- [ ] **Step 3: Animate accent shapes**

Give each accent an explicit frame delay and calculate opacity, translation,
rotation, and scale from `getAccentProgress()`. Do not use CSS animations or
transitions.

- [ ] **Step 4: Type-check the implementation**

Run:

```powershell
npm run typecheck
```

Expected: exit code 0 with no TypeScript errors.

### Task 4: Render and Inspect Key Frames

**Files:**
- Create: `hello-world-video/out/entrance.png`
- Create: `hello-world-video/out/hold.png`
- Create: `hello-world-video/out/exit.png`

- [ ] **Step 1: Render the entrance frame**

Run:

```powershell
npx remotion still src/index.ts HelloWorld out/entrance.png --frame=15
```

Expected: a partially entered title with visible geometric accents.

- [ ] **Step 2: Render the hold frame**

Run:

```powershell
npx remotion still src/index.ts HelloWorld out/hold.png --frame=60
```

Expected: a fully readable, centered title with balanced accents.

- [ ] **Step 3: Render the exit frame**

Run:

```powershell
npx remotion still src/index.ts HelloWorld out/exit.png --frame=112
```

Expected: the scene is visibly fading and shrinking without clipping.

- [ ] **Step 4: Inspect all three images**

Check the exported frames for text clipping, unsafe margins, accidental
overlap, illegible contrast, and unbalanced composition. Adjust
`HelloWorld.tsx` and rerender if any issue is visible.

### Task 5: Render and Verify the MP4

**Files:**
- Create: `hello-world-video/out/hello-world.mp4`

- [ ] **Step 1: Run the complete verification suite**

Run:

```powershell
npm test
npm run typecheck
npx remotion compositions src/index.ts
```

Expected: tests and type checking pass, and `HelloWorld` is listed as
1920 x 1080, 30 fps, 120 frames.

- [ ] **Step 2: Render the final video**

Run:

```powershell
npx remotion render src/index.ts HelloWorld out/hello-world.mp4 --codec=h264
```

Expected: exit code 0 and a non-empty MP4 file.

- [ ] **Step 3: Inspect output metadata**

Use `ffprobe` when available, otherwise inspect the Remotion render output and
file properties. Confirm 1920 x 1080 dimensions, approximately four seconds
duration, and a non-zero file size.

- [ ] **Step 4: Report the deliverable**

Provide the absolute path to `hello-world-video/out/hello-world.mp4`, summarize
verification evidence, and disclose any verification step that could not run.

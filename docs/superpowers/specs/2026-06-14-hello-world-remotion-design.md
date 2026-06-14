# Hello World Remotion Video Design

## Goal

Create a short, self-contained Remotion video that demonstrates a polished
animated "HELLO WORLD!" title and renders to an MP4 file.

## Output

- Composition ID: `HelloWorld`
- Duration: 4 seconds
- Frame rate: 30 fps
- Resolution: 1920 x 1080
- Format: MP4
- Audio: none

## Visual Direction

The video uses a playful pop-art style:

- Warm yellow full-frame background.
- Pink title panel with a thick black border.
- Hard black offset shadow behind the title panel.
- White uppercase `HELLO WORLD!` text in a heavy sans-serif font.
- A small set of black, pink, and white geometric accents around the title.

## Motion

All motion is deterministic and driven by Remotion's frame APIs.

1. During the opening second, the title panel scales up from below its final
   size, rotates toward zero, and settles with a restrained overshoot.
2. Geometric accents enter on slightly offset timings to add energy without
   obscuring the title.
3. The composition holds long enough for the text to remain clearly readable.
4. During the final half-second, the full scene scales down slightly and fades
   out.

CSS transitions and CSS keyframe animations are not used.

## Project Structure

The Remotion project will live in `hello-world-video/` so it remains isolated
from the existing Python application.

- `hello-world-video/src/index.ts`: registers the Remotion root.
- `hello-world-video/src/Root.tsx`: declares the composition metadata.
- `hello-world-video/src/HelloWorld.tsx`: renders the visual scene and motion.
- `hello-world-video/src/HelloWorld.test.ts`: verifies composition constants and
  key timing calculations.
- `hello-world-video/out/hello-world.mp4`: rendered deliverable.

## Verification

- Run the automated tests.
- Run TypeScript and Remotion build checks.
- Render representative still frames near the entrance, hold, and exit.
- Inspect the rendered stills for clipping, readability, balance, and correct
  visual hierarchy.
- Render the complete MP4 and confirm its dimensions, duration, and file size.

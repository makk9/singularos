# SingularOS

A stylized 3D demonstration of an autonomous spacecraft returning to Earth. The
mission discovers available hardware, establishes a position from celestial
observations, plans a trajectory, and returns without a ground link.

The spacecraft, navigation, trajectory, telemetry, and timing are illustrative.
This repository contains the browser demo; it does not implement flight control
or a Linux operating system.

## Development

Requires Node.js 22.12 or newer and pnpm.

```sh
cd web
pnpm install
pnpm dev
```

Open the local URL printed by Vite. Use Pause, Replay, the timeline, or the
mission-phase buttons to inspect the animation. A URL query such as `?t=18.5`
opens a paused view at that second. Reduced-motion preferences start the demo in
a paused view; playback can be started explicitly.

## Simulator

`sim_1/` contains a headless Python 2D simulator for the mission defined in
[MISSION.md](MISSION.md). See [sim_1/README.md](sim_1/README.md) for setup, run and
test commands.

## Verification and deployment

```sh
cd web
pnpm test
pnpm build
pnpm exec wrangler deploy --dry-run
```

`pnpm preview` serves the production build locally. `pnpm deploy` builds the site
and deploys its static assets to the custom domain configured in
`web/wrangler.jsonc`. Cloudflare credentials are required for deployment.

## Implementation

- Three.js renders the spacecraft, globe, Moon, starfield, and navigation guides,
  with material reflections, spacecraft shadows, and HDR bloom on supported GPUs.
- Spacecraft geometry, material detail maps, Moon relief, stars, and the reflection
  environment are generated locally. Small NASA Earth composites are bundled
  with the site; provenance and usage terms are in
  [textures/SOURCES.md](web/public/textures/SOURCES.md).
- `web/src/mission.js` defines the scripted mission and playback clock.
- `web/src/scene.js` builds and animates the 3D scene.
- `web/src/visuals/` supplies the layered Earth shaders, detailed spacecraft,
  and procedural material textures. Effects use mission time so seeking and
  paused frames remain reproducible. Texture arrivals refresh paused views.
- `web/src/main.js` connects playback to the accessible HTML controls and log.
- Vite bundles the dependencies into `web/dist`, which is ignored by Git.
- Google Fonts supplies the typefaces, with local font fallbacks.

If WebGL is unavailable, the mission controls and textual telemetry remain
usable. Graphics-context interruptions pause playback; after recovery, playback
can be resumed explicitly. Narrow views use a lower pixel-ratio ceiling and
smaller shadow maps. Devices without floating-point color-buffer support render
without bloom. This does not guarantee a particular frame rate on every device.

## License

MIT. See [LICENSE](LICENSE). Three.js, Vite, and Wrangler retain their respective
package licenses. The deployed assets include runtime notices in
[THIRD_PARTY_LICENSES.txt](web/public/THIRD_PARTY_LICENSES.txt) and Earth imagery
credits in [textures/SOURCES.md](web/public/textures/SOURCES.md).

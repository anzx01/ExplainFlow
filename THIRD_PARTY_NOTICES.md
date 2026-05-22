# Third-Party Notices

This project is released under the MIT License. Third-party dependencies,
fonts, templates, and assets retain their own licenses and notices.

This file summarizes third-party material that is included in this repository.
It is not a complete inventory of every transitive dependency downloaded by a
package manager.

## Package Dependencies

- Node dependencies for `apps/web` and `apps/render` are listed in their
  respective `package.json` and `package-lock.json` files. Those dependencies
  keep their upstream licenses.
- Python dependencies for `services/api` are listed in `pyproject.toml` and
  `uv.lock`. Those dependencies keep their upstream licenses.
- Remotion packages keep the license terms published by Remotion. Review the
  Remotion license before using hosted or commercial rendering workflows:
  https://github.com/remotion-dev/remotion/blob/main/LICENSE.md

## Bundled Fonts

- `apps/render/public/fonts/Caveat.ttf`
- `apps/render/public/fonts/caveat-400.woff2`
- `apps/render/public/fonts/caveat-700.woff2`
- `apps/render/src/primitives/caveatFont.ts`

These Caveat font files are from the Caveat family distributed through
Google Fonts / `@fontsource/caveat` and are licensed under the SIL Open Font
License 1.1:
https://github.com/google/fonts/tree/main/ofl/caveat

The web app also depends on the `geist` package. It keeps its upstream font
license.

## Template Assets

The SVG files under `apps/web/public/` are default template assets from the
Next.js / Vercel starter and keep their upstream license:
https://github.com/vercel/next.js/blob/canary/license.md

## Project Assets

The following repository-owned binary assets are distributed as part of
ExplainFlow:

- `apps/render/public/hand-real-pen.png`
- `apps/render/public/hand-with-pen.png`
- `image/README/*.png`
- `image/README/*.gif`
- `d2b0a4ac83c8a52341bff172d2749086_30s.gif`
- `pencil-new.pen`

Unless a file-specific notice is added later, these project assets are covered
by the repository's MIT License together with the source code. If any of these
assets are replaced with third-party material, add the relevant attribution and
license notice here before publishing the change.

## Generated Outputs

Generated files are not part of this repository's license unless they are
intentionally committed to the repository. Users are responsible for the rights
and provider terms that apply to their prompts, reference images, generated
images, generated audio, rendered videos, and any other generated output.

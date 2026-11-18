import type { NextConfig } from "next";

const config: NextConfig = {
  // The deliverable is an image somebody installs on a machine inside the plant
  // network (ADR-029), so the runtime stage has to carry the server and nothing
  // else: `standalone` writes a self-contained directory holding only the
  // modules actually reached, and the final image needs neither npm nor a
  // node_modules tree to start.
  output: "standalone",

  // This app is a subdirectory of a larger repository, and the bundler works
  // out its own root by walking up looking for a lockfile. Left to guess it can
  // walk past `web/` entirely and pick up whatever sits above the checkout, so
  // the answer depends on the machine. Say it once instead.
  turbopack: { root: import.meta.dirname },

  // `next build` type-checks as it goes, and it stays on: a build that ignores
  // type errors is a build that has stopped meaning anything. `npm run
  // typecheck` runs the same check on its own so CI can report it as its own
  // red line rather than as a failed build.
  typescript: { ignoreBuildErrors: false },

  // A report may carry one photo (ADR-142). The screen shrinks it to a few
  // hundred kilobytes first; the limit is wide so that a phone whose script did
  // not arrive still gets its report through, and the API, not this parser,
  // refuses the unshrunk picture - a 413 here would lose the words with it.
  experimental: { serverActions: { bodySizeLimit: "12mb" } },
};

export default config;

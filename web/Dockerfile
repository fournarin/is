# The technician's screen, as one image (ADR-008, ADR-029).
#
# It is not the same image as the backend: that one is Python and serves three
# roles from one build (ADR-026); this one is Node and serves one. Nothing is
# shared between them but the network they sit on, and this container never
# reaches `llm-server` at all - the browser talks to this server, this server
# talks to the API, and the API has no route to the model (ADR-003, ADR-058).

FROM node:24-alpine AS deps
WORKDIR /app
# Dependencies in their own layer, from the lockfile only: they change far less
# often than the pages do, so editing a screen does not reinstall the world.
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# `next build` type-checks and lints as it goes (next.config.ts), so a build
# that finishes is a build that passed both.
RUN npm run build

FROM node:24-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Nothing runs as root. The factory host is shared and long-lived, which is the
# same reason the backend image creates its own user.
RUN addgroup --system --gid 10002 web \
    && adduser --system --uid 10002 --ingroup web web

# `output: "standalone"` traces the modules the server actually loads and writes
# them beside it, so what ships is the server and its dependencies rather than
# the whole node_modules tree. The static assets and the public directory are
# not traced and are copied separately - that is the documented shape of a
# standalone build, and forgetting the second COPY gives a site that renders
# with no CSS.
COPY --from=build --chown=web:web /app/.next/standalone ./
COPY --from=build --chown=web:web /app/.next/static ./.next/static

USER web
EXPOSE 3000

# Named explicitly rather than through npm: the standalone build has no npm and
# no package scripts, and a missing entrypoint should fail at build time here
# rather than at boot on somebody else's machine.
CMD ["node", "server.js"]

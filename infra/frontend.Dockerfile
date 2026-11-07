# Frontend image: Next.js standalone server. Dependencies come only from the committed
# package-lock.json (npm ci); the server runs as the unprivileged `node` user.
# node_modules is bind-mounted into the build step rather than copied, which keeps a
# 690 MB layer out of the build cache.
# Build context: frontend/.
FROM node:22.23.3-alpine3.24 AS deps
WORKDIR /srv
COPY package.json package-lock.json ./
# Optional build secret for a network that re-signs HTTPS (see backend.Dockerfile); not stored in the image.
RUN --mount=type=cache,target=/root/.npm --mount=type=secret,id=corp_ca,required=false \
    if [ -f /run/secrets/corp_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/corp_ca; fi; \
    npm ci --prefer-offline --no-audit --no-fund

FROM node:22.23.3-alpine3.24 AS build
WORKDIR /srv
ENV NEXT_TELEMETRY_DISABLED=1
COPY . .
RUN --mount=type=bind,from=deps,source=/srv/node_modules,target=/srv/node_modules --mount=type=secret,id=corp_ca,required=false \
    if [ -f /run/secrets/corp_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/corp_ca; fi; \
    npm run build

FROM node:22.23.3-alpine3.24 AS runtime
LABEL dev.verano.image="frontend"
WORKDIR /srv
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /srv/.next/standalone ./
COPY --from=build --chown=node:node /srv/.next/static ./.next/static
USER node
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD ["wget", "-qO-", "http://127.0.0.1:3000/healthz"]
CMD ["node", "server.js"]

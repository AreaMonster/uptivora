# Uptivora web app (Next.js standalone server).
#   docker build -t uptivora/web:0.1.0 frontend
ARG NODE_IMAGE=node:24-alpine

FROM ${NODE_IMAGE} AS deps
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --ignore-scripts

FROM ${NODE_IMAGE} AS build
WORKDIR /src
# Next.js telemetry stays off during the build as well as at runtime.
ENV NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production
# Server-side address of the API inside the Compose network. Baked into the /api rewrite
# (only used when a request for /api reaches Next.js instead of the reverse proxy).
ARG UPTIVORA_API_INTERNAL_URL=http://api:8000
ENV UPTIVORA_API_INTERNAL_URL=${UPTIVORA_API_INTERNAL_URL}
COPY --from=deps /src/node_modules ./node_modules
COPY . .
RUN mkdir -p public && npm run build

FROM ${NODE_IMAGE} AS runtime
LABEL org.opencontainers.image.title="Uptivora web" \
      org.opencontainers.image.vendor="Uptivora"
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build /src/.next/standalone ./
COPY --from=build /src/.next/static ./.next/static
COPY --from=build /src/public ./public
# npm is not needed at runtime.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx
USER node
EXPOSE 3000
CMD ["node", "server.js"]

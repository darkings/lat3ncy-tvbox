FROM node:22-alpine AS builder

WORKDIR /app
ENV PUPPETEER_SKIP_DOWNLOAD=true
COPY . /app
RUN npm ci --omit=dev --no-audit --fund=false \
    && cp .env.development .env \
    && touch .plugins.js \
    && mkdir -p plugins

FROM node:22-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production TZ=Asia/Shanghai
COPY --chown=node:node --from=builder /app /app
RUN mkdir -p /app/logs /app/data /app/config /app/plugins \
    && chown -R node:node /app/logs /app/data /app/config /app/plugins
USER node
EXPOSE 5757
CMD ["node", "index.js"]

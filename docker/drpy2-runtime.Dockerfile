# DRPYS-only runtime. The separately checked-out upstream source is the build context.
FROM node:22-alpine AS builder

WORKDIR /app
ENV PUPPETEER_SKIP_DOWNLOAD=true
COPY . /app
RUN corepack enable \
    && yarn config set registry https://registry.npmmirror.com \
    && yarn install --production --frozen-lockfile \
    && cp .plugins.example.js .plugins.js \
    && cp .env.development .env \
    && mkdir -p plugins

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production TZ=Asia/Shanghai
COPY --from=builder /app /app
EXPOSE 5757
CMD ["node", "index.js"]

# OFFSCRIPT web - static Next.js export served by nginx (local/demo; Azure uses Static Web Apps)
FROM node:24-alpine AS build
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN npm ci --no-audit --no-fund
COPY packages/contracts packages/contracts
COPY apps/web apps/web
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build -w apps/web

FROM nginx:1.27-alpine
COPY --from=build /repo/apps/web/out /usr/share/nginx/html
EXPOSE 80

FROM node:22.12.0-bookworm-slim AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM scratch AS artifact
COPY --from=build /app/dist /dist

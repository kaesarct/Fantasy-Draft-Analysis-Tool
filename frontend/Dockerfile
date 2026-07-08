# Build di produzione: bundle statico Angular servito da Nginx.
# Il server di sviluppo (`ng serve`, usato da docker-compose.yml) non va esposto
# su internet: i suoi stessi log segnalano "hasn't been reviewed for security issues".

FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npx ng build --configuration production

FROM nginx:alpine
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

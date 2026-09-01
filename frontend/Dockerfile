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
# Garantisce che nginx (worker non privilegiato) possa sempre leggere gli
# asset statici, indipendentemente dai permessi ereditati dal checkout
# sorgente (es. umask della shell non interattiva che esegue il deploy).
RUN chmod -R a+rX /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

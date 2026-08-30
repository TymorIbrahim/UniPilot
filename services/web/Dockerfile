FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Unprivileged nginx: same upstream nginx, but its master process runs as
# uid 101 instead of root, and its writable paths (cache, pid, temp) are
# already owned by that user. Plain `nginx:alpine` starts its master as
# root, which the gallery's compose contract rejects -- and reproducing the
# unprivileged setup by hand means patching the main nginx.conf's `pid`
# and `user` directives, which our conf.d/ server block can't reach.
# Listens on 8080, not 80, because a non-root process can't bind a
# privileged port.
FROM nginxinc/nginx-unprivileged:1.27-alpine
USER nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK CMD test -f /usr/share/nginx/html/index.html

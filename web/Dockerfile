FROM nginxinc/nginx-unprivileged:stable-alpine

LABEL org.opencontainers.image.source="https://github.com/vladmuresan03/engineering-memory"
LABEL org.opencontainers.image.description="Engineering Memory landing page"

COPY out/ /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8175

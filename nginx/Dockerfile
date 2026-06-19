FROM nginx:alpine
RUN apk add --no-cache openssl
COPY 99-generate-cert.sh /docker-entrypoint.d/99-generate-cert.sh
RUN chmod +x /docker-entrypoint.d/99-generate-cert.sh

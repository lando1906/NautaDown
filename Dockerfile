FROM alpine:latest

RUN apk add --no-cache dante-server

COPY sockd.conf /etc/sockd.conf

# Render usa $PORT para web services, pero para SOCKS necesitamos puerto fijo
EXPOSE 1080

CMD ["sockd", "-f", "/etc/sockd.conf", "-N", "1", "-p", "1080"]
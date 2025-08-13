FROM alpine:latest

RUN apk add --no-cache dante-server

# Configura para usar el puerto de Render o 1080
ENV SOCKS_PORT=${PORT:-1080}

COPY sockd.conf /etc/sockd.conf
RUN sed -i "s/port = 1080/port = $SOCKS_PORT/g" /etc/sockd.conf

CMD ["sockd", "-f", "/etc/sockd.conf", "-N", "1"]
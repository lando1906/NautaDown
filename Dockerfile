# Usa Alpine Edge para tener los paquetes más recientes
FROM alpine:edge

# Habilita repositorios comunitarios y actualiza
RUN echo "https://dl-cdn.alpinelinux.org/alpine/edge/main" > /etc/apk/repositories && \
    echo "https://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories && \
    echo "https://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories && \
    apk update && \
    apk add --no-cache \
        shadowsocks-libev \
        v2ray-plugin \
        && mkdir -p /etc/shadowsocks-libev

# Copia la configuración
COPY config.json /etc/shadowsocks-libev/config.json

# Puerto expuesto
EXPOSE 8388

# Comando para iniciar
CMD ["ss-server", "-c", "/etc/shadowsocks-libev/config.json"]
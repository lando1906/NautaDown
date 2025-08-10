# Usa una imagen base más flexible con Alpine Linux
FROM alpine:latest

# Instala Shadowsocks + v2ray-plugin como root
RUN apk add --no-cache \
    shadowsocks-libev \
    v2ray-plugin \
    && mkdir -p /etc/shadowsocks-libev

# Copia la configuración
COPY config.json /etc/shadowsocks-libev/config.json

# Puerto expuesto
EXPOSE 8388

# Comando para iniciar
CMD ["ss-server", "-c", "/etc/shadowsocks-libev/config.json"]
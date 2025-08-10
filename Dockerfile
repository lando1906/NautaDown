FROM shadowsocks/shadowsocks-libev

# Instalar v2ray-plugin (para camuflar tráfico como HTTPS)
RUN apk add --no-cache v2ray-plugin

# Copiar configuración de Shadowsocks
COPY config.json /etc/shadowsocks-libev/config.json

# Puerto expuesto (8388 es el puerto predeterminado de Shadowsocks)
EXPOSE 8388

# Comando para iniciar el servidor
CMD ["ss-server", "-c", "/etc/shadowsocks-libev/config.json"]
FROM alpine:latest

# Instala Dante (SOCKS5) y OpenSSH (para compresión -C)
RUN apk add --no-cache dante-server openssh

# Configura Dante (proxy SOCKS5)
COPY sockd.conf /etc/sockd.conf

# Inicia SOCKS5 + SSH con compresión
CMD ["sh", "-c", "sockd -f /etc/sockd.conf & /usr/sbin/sshd -D -o 'Compression yes'"]
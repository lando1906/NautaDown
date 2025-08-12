FROM alpine:latest

RUN apk add --no-cache dante-server openssh \
    && ssh-keygen -A \  # Genera claves de host para SSH
    && echo "root:password123" | chpasswd  # Establece contraseña para root

COPY sockd.conf /etc/sockd.conf

EXPOSE 1080 22

CMD ["sh", "-c", "sockd -f /etc/sockd.conf & /usr/sbin/sshd -D -o 'Compression yes'"]
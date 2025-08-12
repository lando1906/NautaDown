FROM alpine:latest

RUN apk add --no-cache dante-server openssh && \
    ssh-keygen -A && \
    echo "root:password123" | chpasswd

COPY sockd.conf /etc/sockd.conf

EXPOSE 1080 22

CMD ["sh", "-c", "sockd -f /etc/sockd.conf & /usr/sbin/sshd -D -o 'Compression yes'"]
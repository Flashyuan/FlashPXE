FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends nfs-ganesha nfs-ganesha-vfs rpcbind netbase ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY ganesha.conf /etc/ganesha/ganesha.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh && mkdir -p /srv/synaboot/images

EXPOSE 111/tcp 111/udp 2049/tcp 2049/udp 20048/tcp 20048/udp

ENTRYPOINT ["/entrypoint.sh"]

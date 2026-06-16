FROM alpine:3.20

RUN apk add --no-cache samba-server samba-common-tools
RUN addgroup -S synaboot && adduser -S -D -H -G synaboot -s /sbin/nologin synaboot

COPY smb.conf /etc/samba/smb.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh && mkdir -p /srv/synaboot/images

EXPOSE 445/tcp

ENTRYPOINT ["/entrypoint.sh"]

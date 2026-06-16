#!/bin/sh
set -eu

mkdir -p /run/rpcbind /var/lib/nfs /var/log
rpcbind -w
exec ganesha.nfsd -F -L STDOUT -f /etc/ganesha/ganesha.conf

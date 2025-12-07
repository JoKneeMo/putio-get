#!/usr/bin/env bash
# This script is used to run write the config and start the webdav process
set -e

##### Validation #####
if [ ! -d "${PUTIO_TARGET}" ]; then
    echo -e "\nERROR: ${PUTIO_TARGET} directory does not exist.\nMount point must be added to the container."
    exit 1
fi

if [ -z "${PUTIO_USERNAME}" ]; then
    echo -e "\nERROR: PUTIO_USERNAME is not set."
    exit 1
fi

if [ -z "${PUTIO_PASSWORD}" ]; then
    echo -e "\nERROR: PUTIO_PASSWORD is not set."
    exit 1
fi

##### Write Secrets #####
write_secrets() {
    mkdir -p /etc/davfs2
    echo -e "${PUTIO_DOMAIN}\t${PUTIO_USERNAME}\t${PUTIO_PASSWORD}" > /etc/davfs2/secrets
    chmod 600 /etc/davfs2/secrets
    chown root:root /etc/davfs2/secrets
    unset PUTIO_PASSWORD
}

##### Write Config #####
write_config() {
    echo "[${DAV_MOUNT}]" > /etc/davfs2/davfs2.conf
    echo -n "" > /tmp/davfs2.conf

    for davfs2_var in $(env | grep '^DAVFS2_' | cut -d '=' -f 1); do
        config_key="${davfs2_var#DAVFS2_}"
        config_key="${config_key,,}"
        config_value="${!davfs2_var//\\/\\\\}"
        config_value="${config_value// /\\ }"
        config_value="${config_value//\#/\\#}"
        config_value="${config_value//\"/\\\"}"
        echo "${config_key}  ${config_value}" >> /tmp/davfs2.conf
    done

    awk -F'  ' '{ printf "%-20s %s\n", $1, $2 }' /tmp/davfs2.conf >> /etc/davfs2/davfs2.conf
}

##### Mount WebDAV #####
mount_webdav() {
    mkdir -p ${DAV_MOUNT}

    if [ "$(ls -A ${DAV_MOUNT})" ]; then
        echo -e "\nERROR: ${DAV_MOUNT} is not empty. Please ensure it is empty before starting the container."
        exit 1
    fi

    chown ${DAV_UID}:${DAV_GID} ${DAV_MOUNT}
    rm -f /var/run/mount.davfs/dav.pid
    mount -t davfs -o uid=${DAV_UID},gid=${DAV_GID},dir_mode=${DAV_DMODE},file_mode=${DAV_FMODE} ${PUTIO_DOMAIN} ${DAV_MOUNT}
}

##### Clean Exit on Interrupts #####
clean_exit() {
    int_signal=$1
    echo -e "\nCleaning up..."
    umount ${DAV_MOUNT}
    pkill -${int_signal#SIG} -f "mount.davfs"
    #/var/run/mount.davfs/dav.pid
    sleep 3
    trap - $int_signal
    echo -e "Exiting..."
    exit 0
}

##### Main Execution #####
write_secrets
write_config

trap 'clean_exit SIGINT' SIGINT
trap 'clean_exit SIGTERM' SIGTERM
trap 'clean_exit SIGHUP' SIGHUP
trap 'clean_exit SIGQUIT' SIGQUIT

mount_webdav

##### Execute Docker CMD #####
export PYTHONUNBUFFERED=1
$@

#!/usr/bin/env bash
# Build the two desktop test-bed images from Ubuntu cloud images.
#
# WHY CLOUD IMAGES AND NOT A LIVE ISO
#   The first version of this harness booted a Manjaro GNOME live ISO. That never reached a
#   usable desktop: it has no sshd, the installer is interactive, and the framebuffer went
#   black once GNOME idle-blanked. No distro publishes a prebuilt GNOME desktop qcow2
#   (Fedora ships only Cloud-Base, virt-builder only Server templates, Ubuntu only
#   -server-cloudimg-), so the working route is cloud image + OFFLINE virt-customize
#   --install. Deterministic, no first-boot download, and the result is reusable.
#
# WHY TWO DIFFERENT UBUNTU RELEASES
#   GNOME 50 removed the X11 session entirely — 26.04 has no /usr/share/xsessions at all.
#   So an X11 bed can only be built on <= 24.04, and its GNOME will always trail the
#   Wayland bed's. That is upstream, not a packaging choice we can make differently.
#
# Usage:  ./build.sh wayland | x11 | both
set -euo pipefail

STATE="${SMCP_VM_STATE:-/var/tmp/vmbed}"
KEY="${SMCP_VM_KEY:-$HOME/.ssh/vmbed_ed25519}"
USER_NAME="${SMCP_VM_USER:-tester}"
USER_PASS="${SMCP_VM_PASS:-testpass}"
mkdir -p "$STATE"

_need() {
  for c in qemu-img virt-resize virt-customize curl; do
    command -v "$c" >/dev/null || { echo "missing: $c (install libguestfs-tools)" >&2; exit 1; }
  done
  [ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -f "$KEY"
}

# GDM autologin needs BOTH halves. custom.conf alone does not pick the session type —
# AccountsService does, and .dmrc has been dead for years.
_gdm_conf() { printf '[daemon]\nAutomaticLoginEnable=true\nAutomaticLogin=%s\nWaylandEnable=%s\n' "$USER_NAME" "$1"; }
_acct_conf() { printf '[User]\nSession=%s\nXSession=%s\nSystemAccount=false\n' "$1" "$1"; }

# Idle blanking is what made the old harness look broken: GNOME deactivates the CRTC after
# ~5 min without input, and capture then returns a placeholder (virtio) or a pure black
# frame (std VGA). Kill it in the IMAGE, so no harness-side keepalive is required.
_dconf_db() {
  cat <<'DCONF'
[org/gnome/desktop/session]
idle-delay=uint32 0
[org/gnome/desktop/screensaver]
lock-enabled=false
idle-activation-enabled=false
[org/gnome/settings-daemon/plugins/power]
sleep-inactive-ac-type='nothing'
[org/gnome/desktop/interface]
enable-animations=false
DCONF
}

_build() {  # _build <name> <url> <wayland-enable> <session>
  local name="$1" url="$2" wl="$3" session="$4"
  local base="$STATE/${name}-base.img" disk="$STATE/${name}.qcow2"

  [ -f "$base" ] || curl -fL --progress-bar -o "$base" "$url"
  [ -f "$disk" ] && { echo "  $disk exists — remove it to rebuild"; return 0; }

  qemu-img create -f qcow2 "$disk" 32G >/dev/null
  virt-resize --expand /dev/sda1 "$base" "$disk"

  # Offline install: ~850 packages, several minutes. Separate from the config pass so a
  # config tweak does not re-run the install.
  virt-customize -a "$disk" -m 4096 --smp 4 \
    --install ubuntu-desktop-minimal,openssh-server,pipewire,xdg-desktop-portal-gnome,gnome-remote-desktop

  virt-customize -a "$disk" \
    --root-password password:testroot \
    --run-command "useradd -m -s /bin/bash -G sudo,video,input,render,audio ${USER_NAME} || true" \
    --password "${USER_NAME}:password:${USER_PASS}" \
    --ssh-inject "${USER_NAME}:file:${KEY}.pub" \
    --write "/etc/gdm3/custom.conf:$(_gdm_conf "$wl")" \
    --write "/var/lib/AccountsService/users/${USER_NAME}:$(_acct_conf "$session")" \
    --write "/etc/ssh/sshd_config.d/01-testbed.conf:PasswordAuthentication yes" \
    --write "/etc/dconf/profile/user:user-db:user
system-db:local" \
    --mkdir /etc/dconf/db/local.d \
    --write "/etc/dconf/db/local.d/00-testbed:$(_dconf_db)" \
    --run-command 'dconf update' \
    --run-command 'ssh-keygen -A' \
    --run-command "mkdir -p /home/${USER_NAME}/.config && echo yes > /home/${USER_NAME}/.config/gnome-initial-setup-done && chown -R ${USER_NAME}: /home/${USER_NAME}/.config" \
    --run-command 'systemctl enable ssh; systemctl set-default graphical.target' \
    --run-command 'systemctl disable kdump-tools.service || true' \
    --run-command 'touch /etc/cloud/cloud-init.disabled' \
    --hostname "$name"
  echo "  built $disk"
}

# Three traps, all of which bite silently:
#   ssh-keygen -A      — cloud-init normally generates host keys; disabling cloud-init
#                        without this leaves ssh.service failing to start.
#   01-testbed.conf    — sshd takes the FIRST value obtained and Include sits at the top,
#                        so a 99- drop-in loses to cloud-img's PasswordAuthentication no.
#   --ssh-inject       — the robust path; do not rely on the password alone.

case "${1:-both}" in
  wayland) _need; _build gnome  https://cloud-images.ubuntu.com/resolute/current/resolute-server-cloudimg-amd64.img true  ubuntu ;;
  x11)     _need; _build x11    https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img       false ubuntu-xorg ;;
  both)    "$0" wayland; "$0" x11 ;;
  *) echo "usage: $0 {wayland|x11|both}" >&2; exit 2 ;;
esac

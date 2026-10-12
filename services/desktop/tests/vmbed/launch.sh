#!/usr/bin/env bash
# Boot the two desktop test-bed VMs — one GNOME/Wayland, one GNOME/X11.
#
# Build them first with ./build.sh (cloud image + virt-customize). This script only boots
# what build.sh produced; it no longer touches a live ISO.
#
# WHY NOT A LIVE ISO (the previous design, which never worked)
#   A Manjaro GNOME live ISO has no sshd, an interactive installer, and idle-blanks to a
#   black framebuffer. A lot of time went into "boots but never shows a desktop" before the
#   cause turned out to be GNOME's idle screen blank deactivating the CRTC — not the display
#   device, not the boot. build.sh disables that in the image instead.
#
# WHY UEFI AND NOT SEABIOS — MANDATORY, not a preference.
#   virt-resize renumbers partitions, after which the image's embedded BIOS GRUB no longer
#   resolves and SeaBIOS hangs forever at "Booting from Hard Disk...". The cloud images carry
#   an ESP, so they must be booted through OVMF.
#
# WHY -serial file: UNCONDITIONALLY
#   Ubuntu cloud images already set console=ttyS0 and GRUB_TERMINAL=console, so this costs
#   nothing, and it is the highest-value diagnostic here: it turns "black screen, no idea"
#   into "ssh.service FAILED" in one read.
#
# WHY -vga std AND usb-tablet
#   std keeps a dumpable scanout for the whole boot. usb-tablet is an ABSOLUTE pointer, so a
#   QMP click at (x,y) lands at (x,y) — the default PS/2 mouse is relative and would corrupt
#   exactly the click-accuracy behaviour this bed exists to verify.
#
# Usage:
#   ./launch.sh wayland | x11 | both | status | stop | ssh <bed> [cmd...]
set -euo pipefail

STATE="${SMCP_VM_STATE:-/var/tmp/vmbed}"
KEY="${SMCP_VM_KEY:-$HOME/.ssh/vmbed_ed25519}"
USER_NAME="${SMCP_VM_USER:-tester}"
RAM="${SMCP_VM_RAM:-4096}"
CPUS="${SMCP_VM_CPUS:-4}"
OVMF_CODE="${SMCP_OVMF_CODE:-/usr/share/edk2/x64/OVMF_CODE.4m.fd}"
OVMF_VARS_SRC="${SMCP_OVMF_VARS:-/usr/share/edk2/x64/OVMF_VARS.4m.fd}"

mkdir -p "$STATE"

_qemu() {  # _qemu <name> <disk> <vncdisplay> <sshport>
  local name="$1" disk="$2" vnc="$3" ssh="$4"
  local pidf="$STATE/$name.pid" vars="$STATE/$name-OVMF_VARS.fd"

  if [ -f "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null; then
    echo "  $name already running (pid $(cat "$pidf"))"
    return 0
  fi
  if [ ! -f "$disk" ]; then
    echo "  $name: $disk missing — run ./build.sh first" >&2
    return 1
  fi
  # Per-VM writable UEFI vars; the packaged file is read-only.
  if [ ! -f "$vars" ]; then
    cp "$OVMF_VARS_SRC" "$vars"
    chmod u+w "$vars"
  fi

  qemu-system-x86_64 \
    -name "$name" \
    -enable-kvm -cpu host -smp "$CPUS" -m "$RAM" -machine q35 \
    -drive "if=pflash,format=raw,readonly=on,file=${OVMF_CODE}" \
    -drive "if=pflash,format=raw,file=${vars}" \
    -drive "file=${disk},if=virtio,cache=writeback" \
    -vga std \
    -usb -device usb-tablet -device usb-kbd \
    -netdev "user,id=n0,hostfwd=tcp::${ssh}-:22" -device virtio-net-pci,netdev=n0 \
    -vnc ":${vnc},share=force-shared" \
    -qmp "unix:${STATE}/${name}.qmp,server=on,wait=off" \
    -serial "file:${STATE}/${name}-serial.log" \
    -pidfile "$pidf" \
    -daemonize
  echo "  $name up — vnc :$vnc, ssh -p $ssh ${USER_NAME}@127.0.0.1, serial ${STATE}/${name}-serial.log"
}

_ssh() {
  local bed="${1:-}" port
  case "$bed" in
    wayland) port=22210 ;;
    x11) port=22211 ;;
    *) echo "usage: $0 ssh {wayland|x11} [cmd...]" >&2; return 2 ;;
  esac
  shift
  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 \
    -i "$KEY" -p "$port" "${USER_NAME}@127.0.0.1" "$@"
}

case "${1:-status}" in
  wayland) _qemu gnomevm "$STATE/gnome.qcow2" 10 22210 ;;
  x11)     _qemu x11vm   "$STATE/x11.qcow2"   11 22211 ;;
  both)    "$0" wayland; "$0" x11 ;;
  ssh)     shift; _ssh "$@" ;;
  status)
    for n in gnomevm x11vm; do
      p="$STATE/$n.pid"
      if [ -f "$p" ] && kill -0 "$(cat "$p")" 2>/dev/null; then
        echo "  $n RUNNING pid $(cat "$p")"
      else
        echo "  $n stopped"
      fi
    done
    if command -v ss >/dev/null; then
      ss -ltn 2>/dev/null | grep -E ':(5910|5911|22210|22211)' | sed 's/^/    /' || true
    fi
    ;;
  stop)
    for n in gnomevm x11vm; do
      p="$STATE/$n.pid"
      if [ -f "$p" ] && kill -0 "$(cat "$p")" 2>/dev/null; then
        kill "$(cat "$p")" && echo "  stopped $n"
      fi
      rm -f "$p"
    done
    ;;
  *) echo "usage: $0 {wayland|x11|both|status|stop|ssh <bed> [cmd...]}" >&2; exit 2 ;;
esac

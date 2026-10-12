# vmbed — local VM test beds for the capture backends

Two VMs with real, autologged-in GNOME desktops: one **Wayland**, one **X11**. No second
physical machine, no interactive installer, no human clicking.

This exists because the X11 capture backend was written from measurements taken on a borrowed
host that then became unreachable, and shipped "working" on the strength of unit tests alone.
It was not verified end-to-end until this bed existed — and when it finally ran, it
immediately exposed a real bug (see *What this caught*).

## Use

    ./build.sh both          # one-time: cloud image -> autologin GNOME desktop (slow)
    ./launch.sh both         # boot   (vnc :10/:11, ssh 22210/22211, serial logs)
    ./verify.sh both         # run screen-mcp's backends against both live sessions
    ./launch.sh ssh x11      # shell into a bed
    ./launch.sh stop

`vmctl.py` drives them over QMP with the stdlib only — `screendump` for pixels,
`input-send-event` for absolute pointer and keys:

    ./vmctl.py shot x11 /tmp/x.png
    ./vmctl.py click x11 640 400
    ./vmctl.py consoles x11       # QOM console list; `query-consoles` does not exist

## The beds

| | Wayland | X11 |
|---|---|---|
| Base | Ubuntu 26.04 cloud image | Ubuntu 24.04 cloud image |
| GNOME | Shell 50.1 | Shell 46.0 |
| GStreamer | 1.28.2 | **1.24.2** |
| ssh | `-p 22210 tester@127.0.0.1` | `-p 22211 tester@127.0.0.1` |
| VNC / QMP | `:10` / `gnomevm.qmp` | `:11` / `x11vm.qmp` |

Two different releases on purpose: **GNOME 50 removed the X11 session entirely** (26.04 has
no `/usr/share/xsessions`), so an X11 bed can only be built on <= 24.04 and its GNOME will
always trail the Wayland one. That is upstream, not a choice.

## What `verify.sh` reports (current, both beds live)

|  | Wayland bed | X11 bed |
|---|---|---|
| session | wayland / active | **x11 / active** |
| appsink property chosen | `leaky-type=downstream` | **`drop=true`** |
| our pipeline parses | yes | **yes** |
| portal ScreenCast / RemoteDesktop | present | **present** |
| `AvailableSourceTypes` | 7 | 7 |
| x11capture geometry | `[]` (correct) | `[{0,0,1280,800}]` |
| x11capture grab | None (correct) | **1280x800, sd=18.7, NON_BLANK** |
| AT-SPI apps exposed | 6 | 13 |

## What this caught

1. **The X11 backend works** — first end-to-end run, with pixel-content assertions rather
   than "it returned without raising".
2. **The portal works on GNOME/X11.** ScreenCast + RemoteDesktop are both on the bus with
   `AvailableSourceTypes=7`. The old prereq gate that hard-failed X11 as "Wayland only" was
   wrong in substance, not just in wording.
3. **We were hard-requiring GStreamer >= 1.28 for no reason.** The pipeline named
   `leaky-type=downstream`, which does not exist on 1.24 — the current Ubuntu LTS — so it
   failed to parse outright. 1.28 exposes *both* `drop` and `leaky-type`; the property is now
   chosen at runtime and the floor drops to 1.14-era.
4. **AT-SPI does not need an app restart.** Both beds expose apps (6 and 13) with
   `toolkit-accessibility=false`. The dev host reported 0 only because it sets
   `NO_AT_BRIDGE=1` and `GTK_A11Y=none` in `/etc/environment`.

## Design notes (each of these cost a debugging cycle)

**Cloud image, not a live ISO.** No distro publishes a prebuilt GNOME desktop qcow2, so
`build.sh` does an offline `virt-customize --install`. A live ISO has no sshd and an
interactive installer.

**UEFI, not SeaBIOS — mandatory.** `virt-resize` renumbers partitions, after which the
image's embedded BIOS GRUB no longer resolves and SeaBIOS hangs forever at *"Booting from
Hard Disk..."*. Hence the two `-drive if=pflash` OVMF lines.

**`-serial file:` always.** The cloud images already set `console=ttyS0`, so it is free, and
it is what turns "black screen, no idea" into "`ssh.service` FAILED" in one read.

**Idle blanking is disabled in the image.** GNOME deactivates the CRTC after ~5 min without
input; capture then returns a placeholder (virtio) or a pure black frame (std VGA). That —
not the display device, not the boot — was the cause of the original "boots but never shows a
desktop" dead end. Pointer motion does *not* wake it; only a key event does.

**`-vga std` + `usb-tablet`.** std keeps a dumpable scanout across the whole boot.
`usb-tablet` is an *absolute* pointer, so a QMP click at (x,y) lands at (x,y) — the default
PS/2 mouse is relative and would corrupt the very click-accuracy property under test.

**QMP, not a VNC client library.** `vncdotool` is installed but needs `service_identity`,
which PEP 668 blocks from pip here — a harness that cannot install on the machine it tests is
not a harness. VNC stays exposed for a human viewer.

**Never pass an unchecked `head=` to `screendump`.** A head beyond the device's console count
aborts the whole VM on QEMU 11.0.2. Use `./vmctl.py consoles <bed>` first.

## Known limits

- `/dev/uinput` is not writable in the guests, so the uinput input backend is untested there.
  Input verification currently goes through QMP `input-send-event` instead.
- Guest resolution comes up 1280x800 from bochs-drm defaults; forcing a size (kernel
  `video=`) is untested.
- Pixels have not been pulled through the in-guest PipeWire ScreenCast stream — the portal
  interfaces and source types are proven, the frame path is not.

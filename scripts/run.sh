#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
standalone_root="$(/usr/bin/python3 - "$project_root/scripts" "${ZCODE_STANDALONE_ROOT:-$HOME/.local/share/zcode-on-steroids}" <<'PY'
import os, sys
sys.path.insert(0, sys.argv[1])
from data_backup import namespace_lock, namespace_root, private_dir
root = namespace_root(sys.argv[2])
os.umask(0o077)
with namespace_lock(root, exclusive=False):
    for path in (root, root / 'data/.zcode/v2', root / 'data/.zcode/cli/db', root / 'electron'):
        private_dir(path)
print(root)
PY
)"
export ZCODE_STANDALONE_ROOT="$standalone_root"
export ZCODE_LOCAL_ONLY=1
export ZCODE_DESKTOP_APPLICATION_NAME=zcode-on-steroids
export ZCODE_DATA_BASE_DIR="$standalone_root/data"
export ZCODE_DESKTOP_HOME_DIR="$standalone_root/data"
export DESKTOP_HOME_DIR="$standalone_root/data"
export ZCODE_DESKTOP_USER_DATA_DIR="$standalone_root/electron"
export ZCODE_STORAGE_DIR="$standalone_root/data/.zcode"
export STORAGE_DIR="$standalone_root/data/.zcode"
export ZCODE_SESSION_DB_PATH="$standalone_root/data/.zcode/cli/db/db.sqlite"
# Catatan: `--enable-low-end-device-mode` pernah dinyalakan di sini untuk menghemat ~128 MB
# (876 -> 748 MB PSS), tetapi flag Chromium itu menyentuh perilaku render/hover UI. Default
# dikembalikan ke upstream; tambahkan flag secara manual bila ingin mengujinya lagi.
exec /usr/bin/flock --shared "$standalone_root/../.$(basename "$standalone_root").operations.lock" "$project_root/app/zcode" "$@"

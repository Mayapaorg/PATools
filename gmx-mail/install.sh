#!/bin/sh
# Install the gmxmail command for the current user. No network and no password.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
BIN_DIR=${HOME}/.local/bin
TARGET=$BIN_DIR/gmxmail

if [ "${1:-}" = "--uninstall" ]; then
  if [ -L "$TARGET" ] || [ -f "$TARGET" ]; then
    rm -f "$TARGET"
    echo "Removed $TARGET"
  else
    echo "gmxmail is not installed in $BIN_DIR"
  fi
  exit 0
fi

if [ "${1:-}" != "" ]; then
  echo "Usage: ./install.sh [--uninstall]" >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "gmxmail: python3 is required." >&2
  exit 1
fi

python3 - "$ROOT" <<'PY'
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    found = sys.version.split()[0]
    raise SystemExit(f"gmxmail: Python 3.10 or newer is required (found {found}).")

root = Path(sys.argv[1])
if not (root / "gmxmail" / "__main__.py").is_file():
    raise SystemExit(f"gmxmail: {root} does not contain the gmxmail package.")
PY

mkdir -p "$BIN_DIR"
# The command keeps working if this folder is moved only when the link is
# recreated. The path is written into the launcher on purpose.
cat >"$TARGET" <<EOF
#!/bin/sh
export PYTHONPATH="$ROOT\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m gmxmail "\$@"
EOF
chmod 755 "$TARGET"

echo "Installed $TARGET"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo "Add this to your shell profile, then open a new terminal:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac
echo
echo "Next: gmxmail list --email you@gmx.net"
echo "It asks for the password. Nothing is saved."

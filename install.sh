#!/bin/sh
# Installs nbalake and nba for the current user: curl -fsSL <this file's raw URL> | sh
set -eu

REPO=adamMgross/nbagents
APP="$HOME/.local/share/nbalake-app"
BIN="$HOME/.local/bin"

case "$(uname -s)-$(uname -m)" in
Darwin-arm64) PLATFORM=macos-arm64 ;;
Linux-x86_64) PLATFORM=linux-x86_64 ;;
Linux-aarch64 | Linux-arm64) PLATFORM=linux-arm64 ;;
*)
    echo "nbalake runs on macOS with Apple silicon and on Linux (x86_64 or arm64)." >&2
    exit 1
    ;;
esac
ASSET="nbalake-$PLATFORM.tar.gz"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "Downloading nbalake for $PLATFORM..."
curl -fsSL "https://github.com/$REPO/releases/latest/download/$ASSET" -o "$tmp/$ASSET"
tar -xzf "$tmp/$ASSET" -C "$tmp"

# Apple silicon runs only signed code. An ad-hoc signature needs no Apple account.
if [ "$PLATFORM" = macos-arm64 ] && ! codesign --verify "$tmp/nbalake/nbalake" 2>/dev/null; then
    find "$tmp/nbalake" -type f \( -perm -u+x -o -name '*.dylib' -o -name '*.so' \) \
        -exec codesign --force --sign - {} +
fi

mkdir -p "$(dirname "$APP")" "$BIN"
rm -rf "$APP"
mv "$tmp/nbalake" "$APP"
ln -sf "$APP/nbalake" "$BIN/nbalake"
ln -sf "$APP/nba" "$BIN/nba"

case ":$PATH:" in
*":$BIN:"*) ;;
*)
    case "${SHELL:-}" in
    */zsh) rc="$HOME/.zshrc" ;;
    *) rc="$HOME/.bashrc" ;;
    esac
    line='export PATH="$HOME/.local/bin:$PATH"'
    grep -qsF "$line" "$rc" || printf '\n%s\n' "$line" >>"$rc"
    ;;
esac

"$BIN/nbalake" install-skills

echo
echo "Installed nbalake and nba in $BIN."
echo "Open Claude Code and ask it to set up the NBA lake."

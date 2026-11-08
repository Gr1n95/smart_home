#!/usr/bin/env bash
# Register a locally built or downloaded WordCraft (https://github.com/storytold/wordcraft) in the
# desktop application menu — for Fedora users who cloned the repo instead of installing the .rpm.
#
# It writes the per-user (root not needed) desktop-integration files and refreshes the caches:
#
#   ~/.local/share/applications/ai.storyteller.wordcraft.desktop
#   ~/.local/share/icons/hicolor/<size>x<size>/apps/ai.storyteller.wordcraft.png
#   ~/.local/share/icons/hicolor/scalable/apps/ai.storyteller.wordcraft.svg
#
# Usage:
#   scripts/desktop/install-wordcraft-desktop.sh                  # find the checkout and the binary
#   scripts/desktop/install-wordcraft-desktop.sh --app-dir ~/wordcraft
#   scripts/desktop/install-wordcraft-desktop.sh --bin ~/wordcraft/target/release/wordcraft
#   scripts/desktop/install-wordcraft-desktop.sh --bin ~/Downloads/wordcraft-0.16.0-linux-x86_64.AppImage
#   scripts/desktop/install-wordcraft-desktop.sh --dry-run        # show what would be done
#   scripts/desktop/install-wordcraft-desktop.sh --check          # verify an existing install
#   scripts/desktop/install-wordcraft-desktop.sh --uninstall      # remove the menu entry
#
# Environment: WORDCRAFT_BIN, WORDCRAFT_DIR (same as --bin / --app-dir),
#              XDG_DATA_HOME (default ~/.local/share), HOME.
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$SELF"
APP_ID="ai.storyteller.wordcraft"

BIN=""
APP_DIR=""
MODE=install          # install | uninstall | check
DRY_RUN=0
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS_DIR="$DATA_HOME/applications"
ICONS_DIR="$DATA_HOME/icons/hicolor"
DESKTOP_FILE="$APPS_DIR/$APP_ID.desktop"
TEMPLATE="$SCRIPT_DIR/wordcraft.desktop.in"

die() { echo "error: $*" >&2; exit 1; }
say() { echo "==> $*"; }
note() { echo "    $*"; }
usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin) BIN="${2:-}"; [[ -n "$BIN" ]] || die "--bin needs a path"; shift 2 ;;
    --app-dir) APP_DIR="${2:-}"; [[ -n "$APP_DIR" ]] || die "--app-dir needs a path"; shift 2 ;;
    --uninstall) MODE=uninstall; shift ;;
    --check) MODE=check; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

expand_path() {  # '~', '~/x' and relative paths -> absolute
  local p="$1"
  case "$p" in "~") p="$HOME" ;; "~/"*) p="$HOME/${p#\~/}" ;; esac
  if [[ "$p" != /* ]]; then p="$(cd "$(dirname "$p")" 2>/dev/null && pwd)/$(basename "$p")"; fi
  # collapse "//" and "/./" and resolve ".." lexically (no symlink surprises needed here)
  local out=""
  while [[ "$p" == *//* ]]; do p="${p//\/\///}"; done
  out="$(printf '%s' "$p")"
  printf '%s\n' "$out"
}

# --- locate the wordcraft checkout (icons live in it) -----------------------
is_checkout() { [[ -d "$1/crates/ui-egui" || -d "$1/assets/app-icon" ]]; }

detect_app_dir() {
  local c
  for c in "${WORDCRAFT_DIR:-}" "$APP_DIR" "$HOME/wordcraft" "$HOME/src/wordcraft" \
    "$HOME/git/wordcraft" "$HOME/repos/wordcraft" "$HOME/Downloads/wordcraft" \
    "$HOME/Downloads/wordcraft-master" "$HOME/Downloads/wordcraft-main" "$PWD" "$PWD/wordcraft"; do
    [[ -n "$c" && -d "$c" ]] || continue
    if is_checkout "$c"; then printf '%s\n' "$(expand_path "$c")"; return 0; fi
  done
  return 1
}

# --- locate the executable --------------------------------------------------
detect_bin() {
  local d="$1" c
  if [[ -n "$d" ]]; then
    for c in "$d/target/release/wordcraft" "$d/target/debug/wordcraft"; do
      [[ -x "$c" ]] && { printf '%s\n' "$c"; return 0; }
    done
    while IFS= read -r c; do printf '%s\n' "$c"; return 0; done \
      < <(find "$d" -maxdepth 1 -name '*.AppImage' -type f -perm -u+x 2>/dev/null | sort | head -1)
  fi
  # last resort: a wordcraft already installed system-wide or in ~/.local/bin
  for c in "$(command -v wordcraft 2>/dev/null || true)" "$HOME/.local/bin/wordcraft"; do
    [[ -n "$c" && -x "$c" ]] && { printf '%s\n' "$c"; return 0; }
  done
  return 1
}

resolve_all() {
  [[ -z "$BIN" && -n "${WORDCRAFT_BIN:-}" ]] && BIN="$WORDCRAFT_BIN"

  # An explicitly given binary also tells us where the checkout probably is.
  if [[ -z "$APP_DIR" && -n "$BIN" ]]; then
    local probe; probe="$(expand_path "$BIN")"
    local parent; parent="$(dirname "$probe")"
    local c
    for c in "$parent/../.." "$HOME/wordcraft" "$HOME/Downloads"; do
      if is_checkout "$c"; then APP_DIR="$(expand_path "$c")"; break; fi
    done
  fi
  [[ -z "$APP_DIR" ]] && APP_DIR="$(detect_app_dir || true)"

  if [[ -z "$BIN" ]]; then
    BIN="$(detect_bin "${APP_DIR:-}" || true)"
    [[ -n "$BIN" ]] || die "не нашёл собранный WordCraft. Соберите его ('cd ~/wordcraft && cargo build --release -p wordcraft') или укажите путь: --bin /путь/к/бинарнику"
  fi
  BIN="$(expand_path "$BIN")"
  [[ -e "$BIN" ]] || die "файл не найден: $BIN"
  [[ -f "$BIN" ]] || die "нужен путь к файлу, а не команда: $BIN"
  # A launcher started from a menu has almost no PATH and no shell — the Exec line needs a real file.
  [[ -x "$BIN" ]] || die "файл не исполняемый: $BIN (выполните: chmod +x \"$BIN\")"
}

# --- desktop-entry escaping -------------------------------------------------
# In Exec, a value with spaces must be quoted, and inside quotes \, " and ` and $ are escaped.
exec_quote() {
  local p="$1"
  if [[ "$p" =~ ^[A-Za-z0-9_./+@:,-]+$ ]]; then
    printf '%s' "$p"
  else
    p="${p//\\/\\\\}"; p="${p//\"/\\\"}"; p="${p//\`/\\\`}"; p="${p//\$/\\\$}"
    printf '"%s"' "$p"
  fi
}

run() { if [[ "$DRY_RUN" = 1 ]]; then echo "    [dry-run] $*" >&2; else "$@"; fi; }

refresh_caches() {
  [[ -d "$ICONS_DIR" ]] && command -v gtk-update-icon-cache >/dev/null 2>&1 &&
    { run gtk-update-icon-cache -q -t -f "$ICONS_DIR" >/dev/null 2>&1 || true; }
  [[ -d "$APPS_DIR" ]] && command -v update-desktop-database >/dev/null 2>&1 &&
    { run update-desktop-database -q "$APPS_DIR" >/dev/null 2>&1 || true; }
  # KDE Plasma rebuilds its menu database on demand; ask it now so the entry shows up immediately.
  local k
  for k in kbuildsycoca6 kbuildsycoca5; do
    if command -v "$k" >/dev/null 2>&1; then run "$k" --noincremental >/dev/null 2>&1 || true; break; fi
  done
  return 0
}

install_icons_from() {  # $1 = directory holding <size>x<size>/apps/<id>.png and scalable/
  local src="$1" size n=0
  for size in 16 24 32 48 64 128 256 512; do
    local f="$src/${size}x${size}/apps/$APP_ID.png"
    [[ -f "$f" ]] || continue
    run mkdir -p "$ICONS_DIR/${size}x${size}/apps"
    run install -Dm644 "$f" "$ICONS_DIR/${size}x${size}/apps/$APP_ID.png"
    n=$((n + 1))
  done
  if [[ -f "$src/scalable/apps/$APP_ID.svg" ]]; then
    run install -Dm644 "$src/scalable/apps/$APP_ID.svg" "$ICONS_DIR/scalable/apps/$APP_ID.svg"
    n=$((n + 1))
  fi
  printf '%s\n' "$n"
}

# An AppImage carries the same /usr/share/icons tree inside; unpack just that when there is no
# checkout to copy from (and no FUSE needed: --appimage-extract does its own extraction).
icons_from_appimage() {
  local app="$1" tmpd
  [[ "$app" == *.AppImage ]] || return 1
  tmpd="$(mktemp -d)"
  if (cd "$tmpd" && "$app" --appimage-extract 'usr/share/icons/*' >/dev/null 2>&1) &&
    [[ -d "$tmpd/squashfs-root/usr/share/icons/hicolor" ]]; then
    install_icons_from "$tmpd/squashfs-root/usr/share/icons/hicolor"
    local n=$?
    rm -rf "$tmpd"
    return 0
  fi
  rm -rf "$tmpd"
  return 1
}

# --- modes ------------------------------------------------------------------
do_uninstall() {
  local removed=0 f
  for f in "$DESKTOP_FILE" "$ICONS_DIR"/*/apps/"$APP_ID".png "$ICONS_DIR"/scalable/apps/"$APP_ID".svg; do
    [[ -e "$f" ]] || continue
    run rm -f "$f"; removed=1; note "удалён $f"
  done
  [[ "$removed" = 1 ]] || note "нечего удалять: $DESKTOP_FILE нет"
  refresh_caches
  say "готово: пункт WordCraft убран из меню (само приложение не тронуто)"
}

do_check() {
  local bad=0 exe first
  if [[ ! -f "$DESKTOP_FILE" ]]; then
    note "FAIL  $DESKTOP_FILE отсутствует — запустите скрипт без аргументов"; return 1
  fi
  note "OK    desktop-файл: $DESKTOP_FILE"
  exe="$(sed -n 's/^Exec=//p' "$DESKTOP_FILE" | head -1)"
  note "      Exec: $exe"
  first="${exe%% *}"; first="${first%\"}"; first="${first#\"}"
  if [[ -x "$first" ]]; then note "OK    бинарник на месте: $first"
  else note "FAIL  бинарник отсутствует или не исполняемый: $first"; bad=1; fi
  if [[ -f "$ICONS_DIR/256x256/apps/$APP_ID.png" || -f "$ICONS_DIR/scalable/apps/$APP_ID.svg" ]]; then
    note "OK    иконка установлена"
  else note "FAIL  иконки в $ICONS_DIR нет"; bad=1; fi
  if command -v desktop-file-validate >/dev/null 2>&1; then
    if desktop-file-validate "$DESKTOP_FILE"; then note "OK    desktop-file-validate"
    else note "FAIL  desktop-file-validate"; bad=1; fi
  fi
  if [[ "$bad" = 0 ]]; then say "проверка пройдена"; else say "есть проблемы (см. выше)"; fi
  return "$bad"
}

do_install() {
  resolve_all
  [[ -f "$TEMPLATE" ]] || die "нет шаблона $TEMPLATE (он лежит рядом со скриптом)"

  say "WordCraft: $BIN"
  case "$BIN" in
    */target/debug/*) note "внимание: это debug-сборка; релизная (target/release) стартует заметно быстрее" ;;
  esac
  local ver
  ver="$("$BIN" --version 2>/dev/null | head -1 || true)"
  [[ -n "$ver" ]] && note "версия: $ver"

  # Desktop entry from the template, with the absolute path substituted literally.
  local exec_path tmpd content
  exec_path="$(exec_quote "$BIN")"
  content="$(cat "$TEMPLATE")"
  content="${content//@BIN@/$exec_path}"
  run mkdir -p "$APPS_DIR" "$ICONS_DIR/scalable/apps"
  if [[ "$DRY_RUN" = 1 ]]; then
    echo "    [dry-run] установить $DESKTOP_FILE:"
    printf '%s\n' "$content" | sed 's/^/        /'
  else
    tmpd="$(mktemp)"; printf '%s\n' "$content" >"$tmpd"
    install -Dm644 "$tmpd" "$DESKTOP_FILE"; rm -f "$tmpd"
    note "desktop-файл: $DESKTOP_FILE"
  fi

  # Icons: from the checkout if there is one, otherwise from inside the AppImage.
  local n=0
  if [[ -n "$APP_DIR" && -d "$APP_DIR/assets/app-icon/hicolor" ]]; then
    note "иконки из репозитория: $APP_DIR/assets/app-icon/hicolor"
    n="$(install_icons_from "$APP_DIR/assets/app-icon/hicolor")"
  elif [[ -d "$SCRIPT_DIR/icons/hicolor" ]]; then
    n="$(install_icons_from "$SCRIPT_DIR/icons/hicolor")"
  elif [[ "$DRY_RUN" = 0 ]]; then
    n="$(icons_from_appimage "$BIN" || echo 0)"
    [[ "$n" != 0 ]] && note "иконки распакованы из $BIN"
  fi
  if [[ "$n" = 0 ]]; then
    note "внимание: иконок не нашлось — пункт меню будет со стандартной иконкой"
    note "          (укажите клон репозитория: --app-dir ~/wordcraft)"
  else
    note "иконок установлено: $n"
  fi

  refresh_caches

  if [[ "$DRY_RUN" = 0 ]] && command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$DESKTOP_FILE" || note "внимание: desktop-file-validate нашёл замечания (обычно не мешает)"
  fi

  cat <<EOF

Готово. Как открыть:
  * GNOME:  Super -> наберите «WordCraft» (или Show Apps). Пункт в разделе Office.
  * KDE:    Application Launcher -> Office -> WordCraft.
  * Проверка: $SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}") --check
  * Убрать из меню: $SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}") --uninstall

Если пункт не появился: выйдите из сеанса и войдите снова (Alt+F2, 'r', Enter — только в X11),
а на Fedora AppImage/Linux-сборка требуют установленного fuse (sudo dnf install fuse-libs).
EOF
}

case "$MODE" in
  install) do_install ;;
  uninstall) do_uninstall ;;
  check) do_check ;;
esac

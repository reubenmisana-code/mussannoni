#!/usr/bin/env bash
#
# Provision the system dependencies the conversion pipeline needs.
#
# The pipeline depends on two things that are not Python packages:
#
#   * poppler (pdftoppm) - rasterises the reference and the render at 300 dpi. Both sides must
#     go through the same rasteriser or the metrics measure the font fallback instead of the
#     template.
#   * the licensed Arial and Times New Roman faces - most reports name them without embedding
#     them, and the PDFs carry their advance widths. Laying text out with different metrics
#     makes long strings drift.
#
# Idempotent: safe to re-run. Run it after any environment reset, before `make convert`.
set -euo pipefail

FONT_DIR=/usr/share/fonts/msttcore
WORK_DIR="${TMPDIR:-/tmp}/mussannoni-fonts"

log() { printf '  %s\n' "$*"; }

echo "==> system packages"
if command -v pdftoppm >/dev/null 2>&1; then
  log "poppler already installed ($(pdftoppm -v 2>&1 | head -1))"
else
  dnf install -y poppler-utils >/dev/null 2>&1
  log "installed poppler-utils"
fi

for package in liberation-sans-fonts liberation-serif-fonts cabextract; do
  if rpm -q "$package" >/dev/null 2>&1; then
    log "$package already installed"
  else
    dnf install -y "$package" >/dev/null 2>&1
    log "installed $package"
  fi
done

echo "==> licensed report faces"
if [ -f "$FONT_DIR/arial.ttf" ] && [ -f "$FONT_DIR/times.ttf" ]; then
  log "Arial and Times New Roman already present in $FONT_DIR"
else
  mkdir -p "$WORK_DIR" "$FONT_DIR"
  cd "$WORK_DIR"
  for archive in arial32.exe arialb32.exe times32.exe; do
    if [ ! -f "$archive" ]; then
      curl -sSfL -o "$archive" "https://downloads.sourceforge.net/corefonts/$archive"
      log "downloaded $archive"
    fi
    cabextract -L -q "$archive" >/dev/null
  done
  cp -f ./*.ttf "$FONT_DIR"/
  log "installed $(ls -1 "$FONT_DIR"/*.ttf | wc -l) faces into $FONT_DIR"
fi

fc-cache -f >/dev/null
echo "==> verification"
missing=0
for binary in pdftoppm fc-match; do
  if command -v "$binary" >/dev/null 2>&1; then
    log "$binary ok"
  else
    log "$binary MISSING"
    missing=1
  fi
done

for family in Arial "Arial:bold" "Times New Roman"; do
  resolved=$(fc-match "$family" 2>/dev/null || true)
  log "$family -> $resolved"
  case "$resolved" in
    arial*.ttf*|times*.ttf*) ;;
    *) log "WARNING: '$family' did not resolve to a licensed face; renders will fall back"
       missing=1 ;;
  esac
done

if [ "$missing" -ne 0 ]; then
  echo "environment incomplete - see the warnings above" >&2
  exit 1
fi
echo "environment ready"

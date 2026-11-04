#!/usr/bin/env bash
set -euo pipefail

BADGE_DIR="${1:-./data/badges}"
cd "$BADGE_DIR"

shopt -s nullglob nocaseglob

for img in *.jpg *.jpeg *.png; do
  # Extract the base filename without extension (e.g., "ice_breaker.jpg" -> "ice_breaker")
  base="${img%.*}"
  out="${base}.png"

  echo "Processing: $img -> $out"

  # 1. Resize and center-crop to 256x256
  # 2. Apply hexagonal alpha mask for clean transparent corners
  # 3. Write out as 32-bit PNG (png32: forces an alpha channel even if source is JPG)
  magick "$img" \
    -resize 256x256^ -gravity center -extent 256x256 \
    \( -size 256x256 xc:none -fill white \
       -draw "polygon 128,12 230,68 230,188 128,244 26,188 26,68" \) \
    -alpha off -compose CopyOpacity -composite \
    "png32:${out}"

  # Remove the original file if it was a .jpg or .jpeg
  if [[ "${img,,}" != "${out,,}" ]]; then
    rm -f "$img"
  fi
done

echo "Done! All badges converted to 256x256 transparent PNGs."

#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || -z "$1" ]]; then
    echo "Usage: $0 <outdir>" >&2
    exit 1
fi

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
outdir="$1"
mkdir -p -- "$outdir"
if [[ -n "$(find "$outdir" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "Output directory must be empty: $outdir" >&2
    exit 1
fi

git -C "$repo_root" archive HEAD | tar -x -C "$outdir"
cp -- "$repo_root/deploy/hf-space/README.md" "$outdir/README.md"
# The Hub rejects binary files that are not tracked by LFS/Xet; the Space does not need them.
find "$outdir" -type f -name "*.png" -delete
find "$outdir" -type f -print | sort

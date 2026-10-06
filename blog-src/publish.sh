#!/bin/sh
# Full render, then mirror the output into the directory GitHub Pages serves.
set -e
cd "$(dirname "$0")"
quarto render
rsync -a --delete _site/ ../blog/

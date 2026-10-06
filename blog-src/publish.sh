#!/bin/sh
# Clean full render, mirror the output into the directory GitHub Pages serves,
# and stage everything (including new and deleted files) for commit.
set -e
cd "$(dirname "$0")"
rm -rf _site
quarto render
rsync -a --delete _site/ ../blog/
git add -A . ../blog

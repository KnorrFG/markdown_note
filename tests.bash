#! /bin/bash

if [[ -e ~/.mdnrc ]]; then
    mv ~/.mdnrc ~/.mdnrc.bak
    trap 'mv ~/.mdnrc.bak ~/.mdnrc' EXIT
fi

mdn ls <<'EOF'
~/Sync/mdn.d
nvim {}

EOF


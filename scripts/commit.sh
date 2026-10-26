#!/usr/bin/env bash
#
# Commit with the message read from stdin, so shell quoting can never mangle it.
#
#   scripts/commit.sh <<'EOF'
#   Subject with a visitor's apostrophe
#
#   Body keeps $HOME, `date`, "quotes" — all literal.
#   EOF
#
# Extra arguments are passed straight to `git commit`, so this also works:
#
#   scripts/commit.sh -a <<'EOF'
#   ...
#   EOF
#
# Why not `git commit -m "$(cat <<'EOF' ... EOF)"`, the usual idiom? On the
# /bin/bash macOS ships (3.2) a heredoc inside a command substitution is not
# parsed as a heredoc body: the message is scanned for quote balance, so a lone
# apostrophe ("visitor's") opens a quote that never closes and bash dies with
# "unexpected EOF while looking for matching `''" before git runs. Keeping the
# heredoc at top level and letting this script read it on stdin avoids the
# construct entirely, and `-F` means nothing is re-parsed as shell text.

set -euo pipefail

if [ -t 0 ]; then
    echo "commit: read the message from stdin, for example:" >&2
    echo "  scripts/commit.sh <<'EOF'" >&2
    echo "  Subject line" >&2
    echo "  EOF" >&2
    exit 2
fi

message=$(mktemp "${TMPDIR:-/tmp}/three-step-audit-commit.XXXXXX")
trap 'rm -f "$message"' EXIT

cat >"$message"

if [ ! -s "$message" ]; then
    echo "commit: the message on stdin is empty, so nothing was committed" >&2
    exit 2
fi

git commit -F "$message" "$@"

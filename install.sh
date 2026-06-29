#!/usr/bin/env bash
#
# Install the Datadog site-support auditor into a Claude Code project.
#
#   ./install.sh                 # install into the current project's .claude/
#   ./install.sh --target ~/work/proj
#   ./install.sh --global        # install into ~/.claude (all projects)
#   ./install.sh --yes           # no prompts
#
set -euo pipefail

REPO="jzstur-dd/datadog-site-support-kit"
BRANCH="main"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
step() { printf '\033[1m▸ %s\033[0m\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

# Bootstrap: when piped over curl (no kit files on disk) fetch the repo and
# re-exec the real installer from the clone. Tries gh (handles private repos),
# falls back to anonymous git clone (public repos).
SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo /nonexistent)"
if [ ! -f "$SELF_DIR/.claude/skills/site-support-auditor/SKILL.md" ]; then
  step "Fetching $REPO ..."
  TMP="$(mktemp -d)"
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1 \
       && gh repo clone "$REPO" "$TMP/kit" -- --depth 1 -q >/dev/null 2>&1; then
    ok "cloned via gh"
  elif git clone --depth 1 "https://github.com/$REPO" "$TMP/kit" -q 2>/dev/null; then
    ok "cloned via git"
  else
    echo "error: could not fetch $REPO (private repo without access, or no network)." >&2
    echo "  If private, ask Jackson for collaborator access, or: gh auth login" >&2
    exit 1
  fi
  exec bash "$TMP/kit/install.sh" "$@"
fi

KIT="$SELF_DIR"
TARGET="$PWD"
GLOBAL=0
ASSUME_YES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2;;
    --global) GLOBAL=1; shift;;
    --yes|-y) ASSUME_YES=1; shift;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) warn "unknown flag: $1"; shift;;
  esac
done

command -v python3 >/dev/null 2>&1 || { echo "python3 is required."; exit 1; }

if [ "$GLOBAL" -eq 1 ]; then CLAUDE_DIR="$HOME/.claude"; CLAUDE_MD="$HOME/.claude/CLAUDE.md";
else CLAUDE_DIR="$TARGET/.claude"; CLAUDE_MD="$TARGET/CLAUDE.md"; fi

step "Installing site-support auditor"
printf "  into: %s\n" "$CLAUDE_DIR"
if [ "$ASSUME_YES" -eq 0 ] && [ -t 0 ]; then
  printf "Continue? [Y/n] "; read -r r; case "$r" in [Nn]*) echo aborted; exit 0;; esac
fi

mkdir -p "$CLAUDE_DIR/skills" "$CLAUDE_DIR/commands"
cp -R "$KIT/.claude/skills/site-support-auditor" "$CLAUDE_DIR/skills/"
chmod +x "$CLAUDE_DIR/skills/site-support-auditor/site_support.py"
ok "skill -> $CLAUDE_DIR/skills/site-support-auditor/"
cp "$KIT/.claude/commands/site-support.md" "$CLAUDE_DIR/commands/"
ok "command -> /site-support"
python3 "$KIT/_inject.py" "$CLAUDE_MD" "$KIT/CLAUDE.snippet.md" "ATLAS-GATE"
ok "absence-of-evidence gate -> $CLAUDE_MD"

step "Smoke test (live)"
if python3 "$CLAUDE_DIR/skills/site-support-auditor/site_support.py" verify \
     "https://docs.datadoghq.com/infrastructure/storage_management/" 2>/dev/null \
     | grep -q "gov)  -> 200"; then
  ok "helper reached docs.datadoghq.com and verified a known page"
else
  warn "smoke test could not confirm a 200 (network/proxy?). The skill still"
  warn "installed; try: python3 $CLAUDE_DIR/skills/site-support-auditor/site_support.py list --site gov"
fi

echo ""
step "Installed."
echo "  Restart Claude Code, then try:"
echo "    /site-support list gov"
echo "    /site-support Storage Management"
echo "  or call the helper directly:"
echo "    python3 $CLAUDE_DIR/skills/site-support-auditor/site_support.py find \"Bits AI\""

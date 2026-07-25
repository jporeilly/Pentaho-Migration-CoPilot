#!/usr/bin/env bash
# Pentaho Migration Copilot - uninstaller (Linux / macOS / Git Bash).
# Removes everything the installer created; your source checkout, samples,
# and converted output stay unless you pass --all.
#   --force    skip the confirmation prompt
#   --all      also remove converted output/ and the project database
#   --dry-run  show what would be removed, remove nothing
set -euo pipefail
cd "$(dirname "$0")"

FORCE=0; ALL=0; DRYRUN=0
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        --all) ALL=1 ;;
        --dry-run) DRYRUN=1 ;;
        *) echo "unknown option: $arg (use --force / --all / --dry-run)"; exit 2 ;;
    esac
done

VERSION=$(sed -n 's/^__version__ = "\([0-9.]*\)"/\1/p' src/pentaho_migration/__init__.py 2>/dev/null || echo unknown)
echo
echo "Pentaho Migration Copilot v${VERSION} - uninstall"
echo

targets=(".venv|Python virtual environment"
         "frontend/node_modules|npm packages (UI build deps)"
         "frontend/dist|built web UI"
         ".pytest_cache|test cache")
if [ "$ALL" = 1 ]; then
    targets+=("output|converted .ktr/.kjb/.prpt output (--all)"
              "config/project.db|project store: batch-converted portfolio (--all)")
fi

echo "This removes what install.sh created:"
found=()
for t in "${targets[@]}"; do
    path="${t%%|*}"; why="${t#*|}"
    if [ -e "$path" ]; then
        printf "  - %-24s %s\n" "$path" "$why"
        found+=("$path")
    fi
done
if [ ${#found[@]} -eq 0 ]; then
    echo "  (nothing found - already clean)"; exit 0
fi
echo
if [ "$ALL" = 1 ]; then
    echo "Kept: source code, samples, docs, git history"
else
    echo "Kept: source code, samples, docs, git history, converted output/,"
    echo "      project database (pass --all to remove those too)"
fi
echo

if [ "$DRYRUN" = 1 ]; then
    echo "Dry run - nothing removed."; exit 0
fi
if [ "$FORCE" != 1 ]; then
    read -r -p "Proceed? [y/N] " answer
    case "$answer" in
        y|Y|yes|YES) ;;
        *) echo "Cancelled - nothing removed."; exit 0 ;;
    esac
fi

for path in "${found[@]}"; do
    echo "  removing $path"
    rm -rf "$path"
done
find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true

echo
echo "Uninstalled. To reinstall later: ./install.sh"
echo "To remove the app entirely, delete this folder."

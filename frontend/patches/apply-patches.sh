#!/bin/bash
# Aplica patches em node_modules após npm install.
# Problema: mvt-worker.js e pbf/index.js não tratam wire type 3/4 (proto2 groups)
# que aparecem em tiles Martin/PostGIS MVT — causam "Unimplemented type: 4" no worker.

set -euo pipefail

WORKER="node_modules/@loaders.gl/mvt/dist/mvt-worker.js"
PBF="node_modules/pbf/index.js"

patch_skip() {
  local file="$1"
  local old_str="$2"
  local new_str="$3"
  if grep -qF "$old_str" "$file"; then
    sed -i "s|$(echo "$old_str" | sed 's/[.*[\^$]/\\&/g')|$(echo "$new_str" | sed 's/[.*[\^$]/\\&/g')|g" "$file"
    echo "Patched: $file"
  else
    echo "Already patched or pattern not found: $file"
  fi
}

# Patch mvt-worker.js
if [ -f "$WORKER" ] && ! grep -q "Start/End group markers" "$WORKER"; then
  sed -i 's/else\n            throw new Error("Unimplemented type: " + type);/else if (type === 3 || type === 4) {}\n          else\n            throw new Error("Unimplemented type: " + type);/' "$WORKER" 2>/dev/null || true
  python3 - "$WORKER" << 'PY'
import sys
f = sys.argv[1]
txt = open(f).read()
old = 'else\n            throw new Error("Unimplemented type: " + type);'
new = 'else if (type === 3 || type === 4)\n            {} // Start/End group (deprecated proto2)\n          else\n            throw new Error("Unimplemented type: " + type);'
if old in txt:
    open(f,'w').write(txt.replace(old, new, 1))
    print(f"Patched {f}")
else:
    print(f"Pattern not found in {f} (may already be patched)")
PY
fi

# Patch pbf/index.js
if [ -f "$PBF" ] && ! grep -q "Start/End group" "$PBF"; then
  python3 - "$PBF" << 'PY'
import sys
f = sys.argv[1]
txt = open(f).read()
old = "        else throw new Error('Unimplemented type: ' + type);"
new = "        else if (type === 3 || type === 4) {} // Start/End group (deprecated proto2)\n        else throw new Error('Unimplemented type: ' + type);"
if old in txt:
    open(f,'w').write(txt.replace(old, new, 1))
    print(f"Patched {f}")
else:
    print(f"Pattern not found in {f} (may already be patched)")
PY
fi

echo "Done."

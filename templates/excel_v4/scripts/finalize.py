#!/usr/bin/env python3
"""K1 audit: Open model in Excel, recalculate, save → cached values populated.

Without this step, all 2000+ formulas have empty cached values (<v></v>)
and the file is unverifiable — no one can see if the balance converges.

Usage:
    python scripts/finalize.py model/rusal_v4.xlsx
    python scripts/finalize.py model/nornickel_v4.xlsx

Requires: macOS + Microsoft Excel installed.
"""
import subprocess
import sys
import time
from pathlib import Path


def finalize(xlsx_path: str) -> bool:
    """Open in Excel, recalculate, save, close."""
    path = Path(xlsx_path).resolve()
    if not path.exists():
        print(f"ERROR: {path} not found")
        return False

    print(f"Finalizing: {path}")

    # AppleScript: open → calculate → save → close
    script = f'''
    tell application "Microsoft Excel"
        activate
        open "{path}"
        delay 8
        -- fullCalcOnLoad=1 triggers automatic recalculation on open
        -- Just save to persist cached values
        tell active workbook
            save
        end tell
        delay 3
        close active workbook saving no
        return "saved"
    end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120,
        )
        output = result.stdout.strip()
        print(f"  Excel result: {output}")

        if result.returncode != 0:
            print(f"  WARNING: AppleScript error: {result.stderr[:200]}")
            return False

        # Verify file was actually saved (modification time changed)
        import os
        mtime = os.path.getmtime(str(path))
        if time.time() - mtime > 30:
            print(f"  WARNING: File may not have been saved (mtime too old)")
            return False

        print(f"  ✓ Finalized: cached values saved")
        return True

    except subprocess.TimeoutExpired:
        print("  ERROR: Excel timeout (120s)")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/finalize.py <model.xlsx>")
        sys.exit(1)

    ok = finalize(sys.argv[1])
    sys.exit(0 if ok else 1)

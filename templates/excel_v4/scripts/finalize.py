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
    """Open in Excel, recalculate, save, close. Then fill scenario snapshots."""
    path = Path(xlsx_path).resolve()
    if not path.exists():
        print(f"ERROR: {path} not found")
        return False

    print(f"Finalizing: {path}")

    # AppleScript: open → recalculate → save scenario snapshots → close
    # Runs 3 scenarios: set CP!C5=1/2/3, recalculate, read outputs, paste to 40_Scen
    script = f'''
    tell application "Microsoft Excel"
        activate
        open "{path}"
        delay 8

        set wb to active workbook
        set cpSheet to worksheet "Control_Panel" of wb
        set scenSheet to worksheet "40_Scen" of wb

        -- Find output rows on 40_Scen (section 2: outputs start ~r17)
        -- Read from section 2 (current scenario outputs) for each scenario
        -- and write to section 3 (snapshots)

        -- Column letters for reference
        set colLetters to "ABCDEFGHIJKLM"

        -- Scenario loop: 1=Base, 2=Stress, 3=Severe
        repeat with scIdx from 1 to 3
            set value of cell "C5" of cpSheet to scIdx
            delay 6

            -- Map source output rows to dest snapshot rows
            -- Source: 17=Rev, 18=EBITDA, 19=NI, 20=Cash, 21=Debt, 22=ND/EB, 23=ICR, 24=Margin, 25=Rating
            -- Dest:   29=Rev, 30=EBITDA, 31=NI, 32=Cash, 33=ND/EB, 34=ICR, 35=Rating
            set srcRows to {{17, 18, 19, 20, 22, 23, 25}}
            set dstRows to {{29, 30, 31, 32, 33, 34, 35}}
            repeat with outIdx from 1 to 7
                set srcRow to item outIdx of srcRows
                set dstRow to item outIdx of dstRows
                repeat with yrOff from 0 to 2
                    set srcColIdx to 3 + yrOff
                    set dstColIdx to 3 + ((scIdx - 1) * 3) + yrOff
                    set srcLetter to character srcColIdx of colLetters
                    set dstLetter to character dstColIdx of colLetters
                    try
                        set cellVal to value of range (srcLetter & srcRow) of scenSheet
                        set value of range (dstLetter & dstRow) of scenSheet to cellVal
                    end try
                end repeat
            end repeat
        end repeat

        -- Reset to scenario 1
        set value of cell "C5" of cpSheet to 1
        delay 5

        -- Save
        tell wb to save
        delay 3
        close wb saving no
        return "saved with snapshots"
    end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=300,
        )
        output = result.stdout.strip()
        print(f"  Excel result: {output}")

        if result.returncode != 0:
            print(f"  WARNING: AppleScript error: {result.stderr[:200]}")
            return False

        import os
        mtime = os.path.getmtime(str(path))
        if time.time() - mtime > 30:
            print(f"  WARNING: File may not have been saved (mtime too old)")
            return False

        print(f"  ✓ Finalized: cached values + scenario snapshots saved")
        return True

    except subprocess.TimeoutExpired:
        print("  ERROR: Excel timeout (300s)")
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

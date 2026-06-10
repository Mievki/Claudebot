"""Snel inzicht in state + laatste trades. `python status_cli.py`"""
import json, os
import config as C
import storage as S

def main():
    st = S.load_state()
    print("=== STATE ===")
    print(json.dumps(st, indent=2) if st else "(leeg)")
    print("\n=== LAATSTE TRADES ===")
    if os.path.exists(C.TRADES_CSV):
        lines = open(C.TRADES_CSV).read().strip().splitlines()
        header, rows = lines[0], lines[1:]
        print(header)
        for ln in rows[-10:]:
            print(ln)
    else:
        print("(nog geen trades gelogd)")

if __name__ == "__main__":
    main()

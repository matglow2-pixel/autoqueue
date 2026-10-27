import sys

if sys.platform != "win32":
    raise SystemExit("This desktop application requires Windows 11 and two visible BlueStacks windows.")

from autoqueue.app import main

if __name__ == "__main__":
    main()

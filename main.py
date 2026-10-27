import sys

if sys.platform != "win32":
    raise SystemExit("This desktop application requires Windows 11 and two visible BlueStacks windows.")

try:
    from autoqueue.app import main
except ModuleNotFoundError as error:
    if error.name == "tkinter":
        raise SystemExit('Open the Python installer, choose Modify, enable "tcl/tk and IDLE", and install. Then run setup.bat again.') from None
    raise SystemExit(f"Missing dependency: {error.name}. Run setup.bat again.") from None

if __name__ == "__main__":
    main()

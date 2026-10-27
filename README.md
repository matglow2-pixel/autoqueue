# Sword x Staff Autoqueue

A Windows 11 desktop assistant for two visible BlueStacks instances. No ADB.
You assign one window as the **leader** and the other as the **member**; this must
match the party leader you set in the game. Opening order and window titles do
not decide leadership. The hexadecimal window IDs distinguish identical titles.

The leader opens the dungeon and clicks Match. Both accept matches at least
one second apart. Combat runs using the game's own automatic combat. On results,
the leader likes all detected unclicked teammate buttons and returns. Once the
leader is visibly back, the assistant waits **two seconds**, then handles the
member's likes and return. It repeats without a run limit, including when daily
rewards are exhausted. It waits for the next match after a decline.

## Install on your PC

1. Install **Python 3.12 (64-bit)** from https://www.python.org/downloads/windows/.
   Include the Python launcher (`py`) during installation. This is needed even
   if Python is already installed through the Microsoft Store under another version.
2. Extract the entire project ZIP to a normal folder, for example
   `Documents\SwordStaffAutoqueue`. Do not run it inside the ZIP viewer.
3. Double-click **setup.bat**. This creates a local Python environment and installs
   the pinned dependencies. An Internet connection is needed for this step.
4. Double-click **run.bat** to open the app.

Administrator privileges are normally unnecessary. Run BlueStacks and this app at
the same Windows privilege level. This app uses your mouse: pause it before using
the PC for something else. Your PC must stay awake and unlocked, with both games
visible; this cannot run on a locked desktop or in minimized emulator windows.

## One-time calibration

The reference images in chat are examples, not bundled game-detection assets.
Calibrate the actual game on your PC before the first automated run. Do this
manually through one match; the assistant stays stopped while you capture.

Place both emulators side by side at a comfortable **fixed size**. Keep the same
game resolution, orientation, UI scale, and monitor scaling after calibration.
Windows can move after calibration; resizing requires new calibration. If the
app changes size when moved between monitors with different DPI, recalibrate.

Select the correct windows in the Leader and Member dropdowns. To determine which
window is which, check its title and character in-game. You can temporarily rename
the instances in BlueStacks Multi-instance Manager for clarity, then Refresh windows.
The app lists other desktop windows too; choose the actual game players, not the
Multi-instance Manager. Reassign windows each time the app is launched or BlueStacks
is restarted; old handles are not reused from saved settings.

For each row below:

1. Manually show that game screen on the indicated account.
2. Choose its role and screen name in the app, then **Capture in 3 seconds**.
   The app minimizes. Keep other windows off the game during capture.
3. On the frozen screenshot, **drag a small recognition rectangle**, then release.
4. If the row has an action point, **click once** to mark that point in green.
   These clicks only mark the screenshot; they do not click the live game.
5. Save calibration. Use Reset marks if you marked the wrong place.

| Screen | Accounts | Recognition rectangle | Action point |
| --- | --- | --- | --- |
| `world` | Both | Fixed `Demonseal Gorge` text below minimap; exclude coordinates | Dungeon entrance, in the area you circled |
| `menu` | Leader only | Whole yellow **Match** button, tightly cropped | Center of Match |
| `queue` | Leader | **Cancel** button, tightly cropped; exclude timer | None |
| `queue` | Member | Fixed **Matchmaking…** label on world map; exclude timer | None |
| `accept` | Both | Whole yellow **Accept** button, tightly cropped | Center of Accept |
| `results` | Both | Fixed **Drops** text, tightly cropped | Bottom-left return arrow |
| `like` | Both | One whole white, **unclicked** thumbs-up button, tightly cropped | None |

Both accounts need their own reference crops. Capture accept screens before
accepting manually. The frozen screenshot remains usable after the live countdown
expires. Capture results and like templates **before liking anyone**. Avoid animated
artwork, avatars, changing counters and timers in recognition rectangles.

You can recapture any marker later without clearing the others at the same size.
If the client size changes, the app asks before clearing that account's old markers.
Templates and settings stay locally in `%LOCALAPPDATA%\SwordStaffAutoqueue`.
Only selected crops are saved, not full screenshots. No screenshots are uploaded.

## Verify, then run

Use **Check screens (no clicks)**. The app briefly minimizes, checks both games,
and restores itself. The log should show the actual screen for each account. On a fresh
four-player results screen it should normally report **3 unclicked likes** per
account. If not, recapture `like` before running. Checks require complete
calibration. The live screenshot must be visible even for a no-click check.

Start with both accounts on the outdoor dungeon map, already in the same party,
with the correct fixed leader. Leave **Hard** selected in the dungeon panel
before starting; the assistant does not change difficulty or party membership.

- **F8** or Start/pause: start, pause, or resume. Starting minimizes the app so it
  does not cover a game window.
- **F9** or STOP: stop and reset the session. No further clicks are scheduled.
- Move the mouse to a primary screen corner: PyAutoGUI's failsafe pauses before
  the next click. F9 is the primary emergency stop.

There is at least 0.6 seconds between individual like/return actions to allow UI
updates, one second between accepts, and two seconds between the leader finishing
the return and the member starting results cleanup. Extra waiting may occur for
screen recognition. Results must remain recognized for two seconds so buttons
have time to appear. It never intentionally clicks the member's dungeon or Match.

Watch the first complete automated cycle on your PC. F8 preserves session progress.
After F9, return both accounts manually to the outdoor map before starting a new
session. Do not swap roles or windows during a session; F9 first.

## When it waits or pauses

Combat/loading screens are intentionally `unknown`: the assistant waits without
clicking until a known screen appears. Other unexpected popups can also be unknown;
clear them manually while paused. It cannot distinguish all popups from combat and
does not dismiss them automatically.

If a clicked menu, Match, like, or return action cannot be confirmed visually, it
pauses instead of spamming clicks. A like is considered confirmed only after that
unclicked-button match disappears. Check the log, game screen and reference crops.
If you manually change the game state to recover from a failed confirmation, use
F9, put both accounts back on the outdoor map, then F8 for a new session.

A minimized, closed, resized or visibly covered emulator causes a pause. Windows
focus restrictions can also pause it; focus the game manually and resume. Window
visibility is sampled and the click point is checked again before input; keep
overlays, notifications and other windows away from the games. If F8/F9 are already
registered by another program, startup fails with a message rather than running
without those emergency controls.

## Validation and development

Engine and recognition tests run without BlueStacks:

```sh
python -m unittest discover -s tests -v
```

On Linux, use a virtual environment with Pillow, numpy and opencv-python installed;
the desktop entry point intentionally requires Windows. On Windows, run the tests
with `.venv\Scripts\python.exe -m unittest discover -s tests -v`.

Tests cover sequencing, acceptance spacing, rapid declined-match recovery,
three-player likes, confirmation timeouts, pause timing, queue recognition on the
member's world map, image matching and ambiguous-screen rejection. Image tests use
synthetic fixtures; they do not establish accuracy on the actual game. Windows
window enumeration, focus, screenshots, global hotkeys and mouse injection need
live validation on your PC. They have not been executed in this Linux workspace.

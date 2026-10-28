# Sword x Staff Autoqueue — OCR 1.2

**Choose Leader, choose Member, press Start. No calibration.**

The assistant reads Match, Accept, Cancel, Matchmaking and Drops from the screen
using a bundled, offline OCR engine. It finds the unlabelled like buttons and
bottom-left exit arrow by their shapes. It uses the entrance area from the
Demonseal Gorge layout shown in your screenshots to reopen the dungeon.

## Download and run on Windows 11

1. Download the ZIP from this repository and extract it. When updating, close the
   old app first and replace its project files, or extract to a fresh folder.
2. Double-click **setup.bat**. Run setup again for this version: it installs the
   OCR engine and its models automatically. No Tesseract or model downloads to
   configure separately. Python 3.12 (64-bit), including `tcl/tk and IDLE`, is required.
3. Double-click **run.bat**.
4. Open both BlueStacks game windows side by side. Put both accounts in the same
   party outside Demonseal Gorge. Set the desired difficulty in-game beforehand.
5. Select the window belonging to the in-game party **Leader**, then the other
   window as **Member**. Press **Start** or **F8**. The app minimizes itself.

The window ID after each title distinguishes players with identical names.
Default selections are suggestions; opening order does not decide leadership.
No saved reference images or previous calibration settings are used.

- **F8:** pause/resume.
- **F9:** stop and reset the session.
- After Stop, put both accounts outside the dungeon before starting again.

Both games must stay visible, unlocked and in **English**, with the portrait
layout shown in the screenshots. You can move the windows; after resizing one,
Stop and Start to use its new size. Avoid covering either game with the app,
notifications, overlays or other windows. Run BlueStacks and the assistant at the
same Windows privilege level. The assistant uses your mouse, so pause it before
using the PC for something else. No ADB is required.

## What happens

1. Only the leader opens the dungeon entrance and presses **Match**.
2. Both accounts press **Accept**, at least **0.5 seconds apart**. A declined match
   returns to waiting for the next prompt.
3. Combat runs using the game's automatic combat; this program does not control it.
4. Once results finish appearing, the leader likes all detected available teammates
   and presses the **bottom-left exit arrow**.
5. When the leader is visibly outside, the member immediately starts liking
   teammates and exits. There is no additional handoff delay.
6. Both must be outside before the leader opens the dungeon again. Runs continue
   until stopped, including after daily reward attempts are exhausted.

OCR runs in the background so the control window and stop key remain responsive.
Dungeon, Match, likes and exit have no deliberate per-button cooldown. The loop
checks again after 20 milliseconds plus screen capture/processing time. After OCR
first locates the labels, fresh screenshots validate small label patches instead
of repeatedly running full-window OCR. A changed label triggers OCR again. These
temporary anchors are automatic and kept in memory; no calibration is needed.
Screen capture copies only each game rectangle through MSS, rather than copying
the entire desktop separately for each game. Run setup again to install MSS.
Results use the Drops divider, white unclicked thumbs, dark/gold already-liked
thumbs and normalized exit-arrow silhouettes directly. Missing exit detection no
longer prevents liking teammates. The program waits for each click's visible
effect before the next dependent action, rather than sending a blind click burst.
Actual response time depends on your PC and BlueStacks updating its screen.
When switching accounts, the app temporarily shares Windows input queues to
request focus and waits for activation. If Windows still denies the request,
it can click the visible BlueStacks title bar to activate that window. It then
reads the game screen again before sending the separate game-button click.
This avoids the immediate "Windows blocked focusing the game" pause in the
previous version. Input-queue attachments are released after each focus request.
The app reads a fresh screenshot before clicking a text button. Loading, combat
and unrecognized screens cause waiting without clicks. Failed action confirmations,
covered windows and blocked focus cause a pause with an explanation in the log.
It does not dismiss unrelated popups or change party membership automatically.

## If something does not work

- **Missing tkinter:** reopen the Python installer, choose Modify, enable
  **tcl/tk and IDLE**, and install. Then run setup again.
- **OCR cannot load / missing dependency:** run setup again and read any install
  error. Windows may need the Microsoft Visual C++ 2015–2022 x64 runtime if a DLL
  is reported missing.
- **It waits on a button:** keep the whole window visible, use a readable window
  size, and check that the game is in English. Send a screenshot and the app's
  status/log text if it still fails. You do not need to draw rectangles or teach
  it the buttons.
- **It pauses after clicking:** inspect the game. If you manually change screens
  to recover, Stop, put both accounts outside, then Start a new session.
- **It cannot activate a window:** keep both BlueStacks title bars visible. Run
  both BlueStacks and Autoqueue normally, or at the same administrator permission
  level if you intentionally run BlueStacks as administrator.

Watch the first complete cycle on your PC. The detection is designed for the
Demonseal Gorge UI in the supplied screenshots. Real game fonts, animations,
Windows focus/input and BlueStacks behavior still need validation on your PC.
OCR can misread text, so the app checks context and avoids clicking unrelated
Match/Accept text in chat. Screenshots are processed locally and not uploaded.

## Development checks

```sh
python -m unittest discover -s tests -v
```

Tests cover queue/accept sequencing, half-second acceptance spacing, rapid rematches,
three teammate likes, exit ordering, immediate results handoff, pause timing,
results-button detection at different sizes, already-liked icons, letterboxing,
low-confidence/context rejection and stopping during a blocked OCR read.
An integration test runs the actual bundled OCR models on generated button screens.
It verifies that repeated unchanged screens reuse automatically read labels
without additional OCR inference, and that changed screens invalidate those labels.
Focus regressions cover delayed activation, denied requests, title-bar fallback,
attachment cleanup, cancellation and retrying an unsent click after focus changes.
Those fixtures are not live game captures; passing them does not establish live
BlueStacks accuracy. The Windows desktop adapter cannot execute on Linux.

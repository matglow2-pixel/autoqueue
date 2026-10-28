# Sword x Staff Autoqueue — OCR 1.4

**Choose Leader, choose Member, press Start. No calibration.**

The assistant reads Match, Accept, Cancel, Matchmaking and Drops from the screen
using a bundled, offline OCR engine. It detects the actual white thumbs-up
buttons and clicks the bottom-left exit area. It uses the entrance area from the
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
   returns to waiting for the next prompt. **Matchmaking has no timeout**: queues
   lasting a minute or longer keep running, including when queue OCR is unreadable.
3. Combat runs using the game's automatic combat; this program does not control it.
4. **Member first:** click every detected white thumbs-up icon, then the
   **bottom-left exit button**, as one fast sequence. Up to four actual icons are
   supported; the game's own-player counter and already-gold icons are skipped.
5. **Leader second:** when the member is visibly outside, do the same on the leader.
6. Wait **five seconds after the leader's Exit click** for the dungeon to reload.
   A countdown is shown in the status. Both accounts must be back outside.
7. The leader opens the dungeon again. Runs continue
   until stopped, including after daily reward attempts are exhausted.

OCR runs in the background so the control window and stop key remain responsive.
Accept prompts take priority over all pending click-confirmation checks. The app
can recognize the paired white Decline/yellow Accept buttons even when the dungeon
heading is misread. Small control/minimap crops are read first; a full-frame OCR
pass is only a fallback. Cancel and
Matchmaking detection do not require a correctly read dungeon name. If Match is
still positively visible, failed clicks get up to three attempts; an unknown or
queued screen never triggers that retry limit or a matchmaking timer. Resuming
after other confirmation failures renews their deadlines instead of immediately
pausing again on an already-expired timestamp.
Dungeon, Match, likes and exit have no deliberate per-button cooldown. The loop
checks again after 20 milliseconds plus screen capture/processing time. After OCR
first locates the labels, fresh screenshots validate small label patches instead
of repeatedly running full-window OCR. A changed label triggers OCR again. These
temporary anchors are automatic and kept in memory; no calibration is needed.
Screen capture copies only each game rectangle through MSS, rather than copying
the entire desktop separately for each game. Run setup again to install MSS.
Results use the large rank banner and Drops divider to recognize the end screen
even if individual icon recognition fails. Only white thumb buttons with a dark
icon are clicked; it does not tap avatar positions or the own-player counter.
All detected thumb clicks and Exit run together, with no screenshot, OCR or
color-change confirmation between individual likes. There is a 10 ms input
dispatch interval between taps. Pause/Stop can interrupt the sequence, and a
resumed sequence remembers completed clicks. The exit glyph is used when found;
otherwise the center of the black bottom-left exit button in the supplied layout
is clicked. Cleanup no longer waits for an exact arrow silhouette to match.
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
actual thumb-button detection, member-first cleanup, the five-second reload delay, pause timing,
results-button detection at different sizes, already-liked icons, letterboxing,
low-confidence/context rejection and stopping during a blocked OCR read.
Regression tests simulate long queues without sleeping, late Accept prompts after
an hour, Accept overriding expired confirmations, focused control OCR and resume
after a timeout. These are simulated times, not a live one-hour BlueStacks run.
An integration test runs the actual bundled OCR models on generated button screens.
The runner tests record both accounts' exact click order, verify no OCR between
likes, and check interrupted cleanup resumes without repeating completed clicks.
It verifies that repeated unchanged screens reuse automatically read labels
without additional OCR inference, and that changed screens invalidate those labels.
Focus regressions cover delayed activation, denied requests, title-bar fallback,
attachment cleanup, cancellation and retrying an unsent click after focus changes.
Those fixtures are not live game captures; passing them does not establish live
BlueStacks accuracy. The Windows desktop adapter cannot execute on Linux.

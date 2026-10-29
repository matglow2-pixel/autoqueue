# Sword x Staff Autoqueue — OCR 1.10

**Choose Leader, choose Member, press Start. No calibration.**

The assistant reads Match, Accept, Cancel, Matchmaking and Drops from the screen
using a bundled, offline OCR engine. It detects the actual white thumbs-up
buttons and clicks the bottom-left exit area. It supports dungeons sharing the
game layout shown in your screenshots. The leader opens the gate at your marked
point, about **50.5% across and 34% down** the portrait game viewport, well above
the central character. Dungeon names, minimap labels and cave artwork are not scanned.

## Download and run on Windows 11

1. Download the ZIP from this repository and extract it. When updating, close the
   old app first and replace its project files, or extract to a fresh folder.
2. Double-click **setup.bat**. Run setup again for this version: it installs the
   OCR engine and its models automatically. No Tesseract or model downloads to
   configure separately. Python 3.12 (64-bit), including `tcl/tk and IDLE`, is required.
3. Double-click **run.bat**.
4. Open both BlueStacks game windows side by side. Put both accounts in the same
   party directly in front of your chosen dungeon's gate, with the character in
   the usual central position. Set the desired difficulty in-game beforehand.
5. Select the window belonging to the in-game party **Leader**, then the other
   window as **Member**. Press **Start** or **F8**. The control window stays open
   when starting or resuming; place it beside the games so all three stay visible.

The window ID after each title distinguishes players with identical names.
Default selections are suggestions; opening order does not decide leadership.
No saved reference images or previous calibration settings are used.

- **F8:** pause/resume.
- **F9:** stop and reset the session.
- After Stop, put both accounts outside the dungeon before starting again.
- When updating from a stuck results screen, exit those old results manually
  once and start a fresh run outside; the new app cannot recover old click history.

Both games must stay visible, unlocked and in **English**, with the portrait
layout shown in the screenshots. You can move the windows; after resizing one,
Stop and Start to use its new size. Avoid covering either game with the app,
notifications, overlays or other windows. Run BlueStacks and the assistant at the
same Windows privilege level. The assistant uses your mouse, so pause it before
using the PC for something else. No ADB is required.

## What happens

1. Only the leader opens the dungeon entrance and presses **Match**. If an entrance
   tap is ignored, it retries your marked point **two seconds apart, up to three
   total attempts**, only while the outside HUD is visible. Loading/unreadable
   screens keep waiting without a ten-second entrance-confirmation timer.
2. Both accounts press **Accept**, at least **1.5 seconds apart**. A declined match
   returns to waiting for the next prompt. **Matchmaking has no timeout**: queues
   lasting a minute or longer keep running, including when queue OCR is unreadable.
   A still-active yellow Accept button is retried if BlueStacks missed the tap.
   Each account gets its first attempt before retries; disabled buttons are skipped.
3. Combat runs using the game's automatic combat; this program does not control it.
4. **Member first:** wait **one second after its end screen appears**, read
   the buttons again, and click every detected white thumbs-up icon. Pause a
   fresh random **0.2–0.5 seconds between likes**. Verify the batch, then press the
   **bottom-left exit button**. Up to four actual icons are
   supported; the game's own-player counter and already-gold icons are skipped.
5. **Leader second:** switch as soon as the member's Exit click is sent, without
   waiting for the member to load outside. Do the same with a **one-second end-screen
   wait**. This wait is measured from when the leader's results first appeared, so it may
   already have elapsed while the member was handled.
6. Wait **five seconds after the leader's Exit click** for the dungeon to reload.
   A countdown is shown in the status. Both accounts must be back outside.
7. The leader opens the dungeon again. Runs continue
   until stopped, including after daily reward attempts are exhausted.

OCR runs in the background so the control window and stop key remain responsive.
Accept prompts take priority over all pending click-confirmation checks. The app
can recognize the paired white Decline/yellow Accept buttons even when the dungeon
heading is missing. Small control crops are read first; a full-frame OCR
pass is only a fallback. Cancel and
Matchmaking detection do not require a correctly read dungeon name. If Match is
still positively visible, failed clicks get up to three attempts; an unknown or
queued screen never triggers that retry limit or a matchmaking timer. Resuming
after confirmation failures renews cleanup deadlines or rearms click retries
instead of immediately pausing again on an old failure.
The first entrance click and the Match click have no deliberate cooldown. Retries
wait two seconds so the game can respond. The loop
checks again after 20 milliseconds plus screen capture/processing time. After OCR
first locates the labels, fresh screenshots validate small label patches instead
of repeatedly running full-window OCR. A changed label triggers OCR again. These
temporary anchors are automatic and kept in memory; no calibration is needed.
An appearing yellow action button invalidates a cached outside screen, so a new
Match/Accept menu is read even if its background still shows the Explore label.
Screen capture copies only each game rectangle through MSS, rather than copying
the entire desktop separately for each game. Run setup again to install MSS.
Results use the large rank banner and Drops divider to recognize the end screen
even if individual icon recognition fails. Gold reward badges on the queue screen
cannot substitute for the results banner. Only white thumb buttons with a dark
icon are clicked; it does not tap avatar positions or the own-player counter.
Thumb clicks run as a batch with the requested random spacing, without OCR
between individual likes. The mouse moves for a random 100–180 ms toward each
target, and presses last a random 40–80 ms so BlueStacks can register the down/up
events. One check after the batch confirms likes before Exit.
Still-white thumbs are retried up to twice; uncertain detection keeps results
open instead of exiting. The app remembers the white button areas before clicking
and checks that each successfully clicked white control disappears. Gold thumbs
show **received likes** and have no role in confirming the account's outgoing
likes. An empty initial scan without click history cannot authorize Exit.
Buttons are searched over a wider row area with more tolerance for dimmer rendering.
Pause/Stop can interrupt the sequence, and a
resumed sequence remembers completed clicks. The exit glyph is used when found;
otherwise the center of the black bottom-left exit button in the supplied layout
is clicked. Cleanup no longer waits for an exact arrow silhouette to match.
Actual response time depends on your PC and BlueStacks updating its screen.
If recognition remains uncertain, a local screenshot is saved under
`%LOCALAPPDATA%\SwordStaffAutoqueue\debug` and its path is printed in the log.
Screenshots are not uploaded. The app keeps the results open so the failure can
be inspected instead of silently skipping likes.
When switching accounts, the app temporarily shares Windows input queues to
request focus and waits for activation. If Windows still denies the request,
it can click the visible BlueStacks title bar to activate that window. It then
reads the game screen again before sending the separate game-button click.
This avoids the immediate "Windows blocked focusing the game" pause in the
previous version. Input-queue attachments are released after each focus request.
The app reads a fresh screenshot before clicking a text button. Loading, combat
and unrecognized screens cause waiting without clicks. Temporarily covered windows
are skipped until visible again, with automatic recovery and no manual resume.
An uncovered account can still Accept while the other is covered. No input is sent
to covered targets; focus and visibility are checked again after mouse movement.
Failed action confirmations and blocked focus cause a pause with an explanation in the log.
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

Watch the first complete cycle on your PC. Dungeon names and entrance artwork
do not affect the shared UI detection. The entrance position uses the gate layout
you supplied rather than tracking the character; start while standing at the gate.
Real game fonts, animations,
Windows focus/input and BlueStacks behavior still need validation on your PC.
OCR can misread text, so the app checks context and avoids clicking unrelated
Match/Accept text in chat. Screenshots are processed locally and not uploaded.

## Development checks

```sh
python -m unittest discover -s tests -v
```

Tests cover queue/accept sequencing, 1.5-second acceptance spacing, rapid rematches,
actual thumb-button detection, member-first cleanup, one-second end-screen waits,
random like intervals, the five-second reload delay, pause timing,
results-button detection at different sizes, already-liked icons, letterboxing,
low-confidence/context rejection and stopping during a blocked OCR read.
Regression tests simulate long queues without sleeping, late Accept prompts after
an hour, Accept overriding expired confirmations, focused control OCR and resume
after a timeout. These are simulated times, not a live one-hour BlueStacks run.
An integration test runs the actual bundled OCR models on generated button screens.
The runner tests record both accounts' exact click order, verify no OCR between
individual likes, retry unregistered likes before Exit, and check interrupted
cleanup resumes without repeating completed clicks. Unknown zero scans are
tested to prohibit Exit. Removal of the clicked buttons is tested with zero, two,
or three incoming gold indicators, which are deliberately irrelevant to completion.
A generated-screen replay removes all outgoing buttons while keeping two incoming
indicators, then verifies Exit and handoff through both accounts.
It verifies that repeated unchanged screens reuse automatically read labels
without additional OCR inference, and that changed screens invalidate those labels.
Focus regressions cover delayed activation, denied requests, title-bar fallback,
attachment cleanup, cancellation and retrying an unsent click after focus changes.
Those fixtures are not live game captures; passing them does not establish live
BlueStacks accuracy. The Windows desktop adapter cannot execute on Linux.
Regression coverage includes three consecutive complete cycles, a leader Accept
tap and entrance tap ignored by the game in the second cycle, visibility recovery, and accepting
on the uncovered account while its partner is temporarily covered.
Dungeon-independent tests cover missing and different headings, the marked point
at several sizes and within letterboxing, and rejection of Explore text in chat.
The real OCR models also read the common controls on screens with no dungeon name.
Entrance regressions cover bounded retries, indefinite waiting during unreadable
transitions, entering a queue without observing its menu frame, and a new Match
button overriding a cached outside HUD. The real OCR replay leaves Explore
visible beneath menus to exercise that transition.

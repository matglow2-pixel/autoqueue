import queue
import threading
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
import numpy as np

from autoqueue.engine import Action, View, SafetyStop, WindowUnavailable
from autoqueue.runner import Control, Runner, action_point, cleanup_points
from autoqueue.vision import results_fast


def results_view():
    return View('results', targets={
        'like_1': (100, 715), 'like_2': (250, 715), 'like_3': (400, 715),
        'like_4': (520, 715), 'return': (66, 1050)})


class FakeWindow:
    def __init__(self):
        self.clicks = []

    def capture(self):
        return Image.new('RGB', (600, 1100))

    def focus(self, allowed):
        if not allowed():
            raise RuntimeError('Stopped before focus')

    def click(self, point, **kwargs):
        self.clicks.append(point)


class RunnerTests(unittest.TestCase):
    def test_three_cycles_recover_a_missed_gate_click_and_accept_in_second_cycle(self):
        states = {'leader': 'world', 'member': 'world'}
        remaining = {}
        clock = [0.0]
        cycles = [0]
        missed = [False]
        missed_gate = [False]
        actions = []
        class CycleOCR:
            def inspect(self, image, role='default'):
                state = states[role]
                if state == 'results':
                    targets = {f'like_{i+1}': p for i, p in enumerate(remaining[role])}
                    targets['return'] = (66, 1050)
                    return View('results', likes=remaining[role].copy(), targets=targets,
                                likes_cleared=not remaining[role])
                return View(state, targets={'world': {'dungeon': (300, 380)},
                                            'menu': {'match': (450, 950)},
                                            'accept': {'accept': (450, 980)}}.get(state, {}))
        class CycleWindow(FakeWindow):
            def __init__(self, role):
                super().__init__()
                self.role = role

            def capture(self):
                clock[0] += .1
                return super().capture()

            def click(self, point, **kwargs):
                role, state = self.role, states[self.role]
                actions.append((cycles[0], role, state, point, clock[0]))
                if state == 'world':
                    if cycles[0] == 1 and not missed_gate[0]:
                        missed_gate[0] = True
                    else:
                        states[role] = 'menu'
                elif state == 'menu':
                    states.update(leader='accept', member='accept')
                    for r in states:
                        remaining[r] = list(cleanup_points(results_view())[:-1])
                elif state == 'accept':
                    if cycles[0] == 1 and role == 'leader' and not missed[0]:
                        missed[0] = True  # Sent successfully, but ignored by the game.
                    else:
                        states[role] = 'accepted'
                    if all(s == 'accepted' for s in states.values()):
                        states.update(leader='results', member='results')
                elif state == 'results':
                    if point == (66, 1050):
                        states[role] = 'loading'
                        if role == 'leader':
                            cycles[0] += 1
                            states.update(leader='world', member='world')
                            if cycles[0] == 3:
                                runner.control.stop()
                    else:
                        remaining[role].remove(point)
                return True
        windows = {r: CycleWindow(r) for r in states}
        events = queue.SimpleQueue()
        runner = Runner(windows, events, recognizer_factory=CycleOCR, like_delay=lambda: 0)
        runner.control.now = lambda: clock[0]
        runner.start()
        runner.join(5)
        try:
            self.assertFalse(runner.is_alive())
            self.assertEqual(cycles[0], 3)
            accepts = [a for a in actions if a[2] == 'accept']
            self.assertEqual([a[1] for a in accepts],
                             ['leader', 'member', 'leader', 'member', 'leader', 'leader', 'member'])
            self.assertTrue(all(b[-1] - a[-1] >= 1.5 for a, b in zip(accepts, accepts[1:])))
            gate_clicks = [a for a in actions if a[2] == 'world']
            self.assertEqual([a[0] for a in gate_clicks], [0, 1, 1, 2])
            self.assertTrue(all(a[1] == 'leader' for a in gate_clicks))
            self.assertGreaterEqual(gate_clicks[2][-1] - gate_clicks[1][-1], 2)
            for cycle in (0, 1):
                leader_exit = next(a[-1] for a in actions if a[:3] == (cycle, 'leader', 'results')
                                   and a[3] == (66, 1050))
                next_dungeon = next(a[-1] for a in actions if a[:3] == (cycle+1, 'leader', 'world'))
                self.assertGreaterEqual(next_dungeon - leader_exit, 5)
            messages = []
            while not events.empty():
                messages.append(events.get_nowait())
            self.assertFalse(any(kind == 'paused' for kind, _ in messages))
        finally:
            runner.control.stop()
            runner.join(2)

    def test_covered_leader_recovers_without_pausing_or_blocking_member(self):
        clock = [0.0]
        clicks = []
        states = {'leader': 'accept', 'member': 'accept'}
        class AcceptOCR:
            def inspect(self, image, role='default'):
                return View(states[role], targets={'accept': (450, 980)})
        class CoveredWindow(FakeWindow):
            captures = 0
            def __init__(self, role):
                super().__init__()
                self.role = role
            def capture(self):
                clock[0] += .5
                self.captures += 1
                if self.role == 'leader' and self.captures <= 3:
                    raise WindowUnavailable('another window covers the game')
                return super().capture()
            def click(self, point, **kwargs):
                clicks.append(self.role)
                states[self.role] = 'accepted'
                if len(clicks) == 2:
                    runner.control.stop()
                return True
        events = queue.SimpleQueue()
        runner = Runner({r: CoveredWindow(r) for r in states}, events, recognizer_factory=AcceptOCR)
        runner.control.now = lambda: clock[0]
        runner.start()
        runner.join(3)
        try:
            self.assertFalse(runner.is_alive())
            self.assertEqual(clicks, ['member', 'leader'])
            messages = []
            while not events.empty():
                messages.append(events.get_nowait())
            self.assertFalse(any(kind == 'paused' for kind, _ in messages))
            self.assertEqual(sum('waiting for visibility' in msg for _, msg in messages), 1)
            self.assertTrue(any('visible again' in msg for _, msg in messages))
        finally:
            runner.control.stop()
            runner.join(2)

    def test_match_click_commits_without_a_matchmaking_deadline(self):
        class MenuOCR:
            def inspect(self, image, role="default"):
                return View('menu', targets={'match': (450, 950)}) if role == 'leader' else View('world')
        class MatchWindow(FakeWindow):
            def click(self, point, **kwargs):
                self.clicks.append(point)
                runner.control.stop()
                return True
        windows = {'leader': MatchWindow(), 'member': FakeWindow()}
        runner = Runner(windows, queue.SimpleQueue(), recognizer_factory=MenuOCR)
        runner.start()
        runner.join(3)
        try:
            self.assertFalse(runner.is_alive())
            self.assertEqual(windows['leader'].clicks, [(450, 950)])
            self.assertEqual(runner.engine.pending[0].kind, 'match')
            self.assertIsNone(runner.engine.pending[1])
        finally:
            runner.control.stop()
            runner.join(2)

    def test_lost_focus_does_not_commit_an_unsent_game_click(self):
        order = []
        class WorldOCR:
            def inspect(self, image, role="default"):
                order.append('read')
                return View('world', targets={'dungeon': (300, 380)})
        class FocusWindow(FakeWindow):
            def focus(self, allowed):
                super().focus(allowed)
                order.append('focus')

            def click(self, point, **kwargs):
                order.append('click')
                self.clicks.append(point)
                if len(self.clicks) == 1:
                    return False  # Desktop focus changed before sending input.
                runner.control.stop()
                return True
        windows = {'leader': FocusWindow(), 'member': FakeWindow()}
        runner = Runner(windows, queue.SimpleQueue(), recognizer_factory=WorldOCR)
        runner.start()
        runner.join(3)
        try:
            self.assertFalse(runner.is_alive())
            self.assertEqual(windows['leader'].clicks, [(300, 380), (300, 380)])
            self.assertEqual(order[:5], ['read', 'read', 'focus', 'read', 'click'])
            self.assertEqual(runner.engine.pending[0].kind, 'dungeon')
        finally:
            runner.control.stop()
            runner.join(2)

    def test_stop_during_slow_ocr_cancels_planned_mouse_input(self):
        entered, release = threading.Event(), threading.Event()
        class SlowOCR:
            def inspect(self, image, role="default"):
                entered.set()
                if not release.wait(2):
                    raise RuntimeError('Test OCR timed out')
                return View('world', targets={'dungeon': (300, 380)})
        windows = {'leader': FakeWindow(), 'member': FakeWindow()}
        runner = Runner(windows, queue.SimpleQueue(), recognizer_factory=SlowOCR)
        runner.start()
        try:
            self.assertTrue(entered.wait(2))
            runner.control.stop()
        finally:
            release.set()
            runner.join(3)
        self.assertFalse(runner.is_alive())
        self.assertFalse(windows['leader'].clicks)
        self.assertFalse(windows['member'].clicks)

    def test_paused_clock_excludes_time_spent_paused(self):
        control = Control()
        with patch('autoqueue.runner.time.monotonic', return_value=10):
            self.assertEqual(control.now(), 10)
            control.pause()
        with patch('autoqueue.runner.time.monotonic', return_value=100):
            self.assertEqual(control.now(), 10)
            control.resume()
            self.assertEqual(control.now(), 10)
        with patch('autoqueue.runner.time.monotonic', return_value=101):
            self.assertEqual(control.now(), 11)

    def test_fresh_screen_must_still_authorize_the_planned_action(self):
        action = Action('leader', 'match')
        self.assertIsNone(action_point(action, View('queue')))
        self.assertIsNone(action_point(action, View('menu')))
        self.assertEqual(action_point(action, View('menu', targets={'match': (450, 950)})), (450, 950))
        self.assertIsNone(cleanup_points(View('world')))
        self.assertIsNone(cleanup_points(View('results', likes_ready=False)))
        self.assertEqual(cleanup_points(results_view()),
                         ((100, 715), (250, 715), (400, 715), (520, 715), (66, 1050)))

    def test_cleanup_clicks_all_detected_icons_then_exit_without_more_ocr(self):
        windows = {'leader': FakeWindow(), 'member': FakeWindow()}
        runner = Runner(windows, queue.SimpleQueue(), like_delay=lambda: 0)
        runner.sizes['member'] = (600, 1100)
        runner.observe = lambda role: View('results', targets={'return': (66, 1050)}, likes_cleared=True)
        view = results_view()
        self.assertTrue(runner.cleanup('member', view))
        self.assertEqual(windows['member'].clicks, list(cleanup_points(view)))
        self.assertEqual(windows['leader'].clicks, [])
        self.assertTrue(runner.cleanup('member', view))
        self.assertEqual(len(windows['member'].clicks), 5)

    def test_cleanup_stop_interrupts_before_exit(self):
        class StoppingWindow(FakeWindow):
            def click(self, point, **kwargs):
                self.clicks.append(point)
                if len(self.clicks) == 2:
                    runner.control.stop()
                return True
        window = StoppingWindow()
        runner = Runner({'leader': FakeWindow(), 'member': window}, queue.SimpleQueue(), like_delay=lambda: 0)
        runner.sizes['member'] = (600, 1100)
        self.assertFalse(runner.cleanup('member', results_view()))
        self.assertEqual(window.clicks, [(100, 715), (250, 715)])

    def test_cleanup_retains_progress_when_focus_is_lost(self):
        class InterruptedWindow(FakeWindow):
            failed = False
            def click(self, point, **kwargs):
                if len(self.clicks) == 2 and not self.failed:
                    self.failed = True
                    return False
                self.clicks.append(point)
                return True
        window = InterruptedWindow()
        runner = Runner({'leader': FakeWindow(), 'member': window}, queue.SimpleQueue(), like_delay=lambda: 0)
        runner.sizes['member'] = (600, 1100)
        self.assertFalse(runner.cleanup('member', results_view()))
        # Already-liked icons can disappear from a later screenshot. Continue
        # the original authorized sequence without double-clicking prior icons.
        changed_view = View('results', targets={'like_1': (400, 715), 'return': (66, 1050)})
        runner.observe = lambda role: View('results', targets={'return': (66, 1050)}, likes_cleared=True)
        self.assertTrue(runner.cleanup('member', changed_view))
        self.assertEqual(window.clicks, list(cleanup_points(results_view())))

    def test_member_exit_hands_off_while_member_is_still_loading(self):
        states = {'leader': 'results', 'member': 'results'}
        clicks = []
        reads = []
        trace = []
        exit_times = {}
        remaining = {r: list(cleanup_points(results_view())[:-1]) for r in states}
        class ResultsOCR:
            def inspect(self, image, role='default'):
                reads.append(role)
                trace.append(('read', role))
                if states[role] == 'loading':
                    return View('unknown')
                if states[role] != 'results':
                    return View('world')
                targets = {f'like_{i+1}': p for i, p in enumerate(remaining[role])}
                targets['return'] = (66, 1050)
                return View('results', likes=remaining[role].copy(), targets=targets, likes_cleared=not remaining[role])
        class ResultsWindow(FakeWindow):
            def __init__(self, role):
                super().__init__()
                self.role = role

            def click(self, point, **kwargs):
                clicks.append((self.role, point))
                trace.append(('click', self.role, point))
                if point in remaining[self.role]:
                    remaining[self.role].remove(point)
                if point == (66, 1050):
                    states[self.role] = 'loading' if self.role == 'member' else 'world'
                    exit_times[self.role] = runner.control.now()
                    if self.role == 'leader':
                        runner.control.stop()
                return True
        windows = {r: ResultsWindow(r) for r in states}
        runner = Runner(windows, queue.SimpleQueue(), recognizer_factory=ResultsOCR, like_delay=lambda: 0)
        runner.start()
        runner.join(3)
        try:
            self.assertFalse(runner.is_alive())
            points = cleanup_points(results_view())
            self.assertEqual(clicks, [('member', p) for p in points] + [('leader', p) for p in points])
            self.assertEqual(states['member'], 'loading')
            for role in states:
                indices = [i for i, event in enumerate(trace) if event[0] == 'click'
                           and event[1] == role and event[2] != (66, 1050)]
                self.assertEqual(indices[-1] - indices[0], 3)  # No OCR between four likes.
            self.assertGreaterEqual(runner.engine.requeue_at, exit_times['leader'] + 5)
        finally:
            runner.control.stop()
            runner.join(2)

    def test_random_pause_between_each_like_is_in_requested_range(self):
        runner = Runner({'leader': FakeWindow(), 'member': FakeWindow()}, queue.SimpleQueue())
        runner.sizes['member'] = (600, 1100)
        runner.observe = lambda role: View('results', targets={'return': (66, 1050)}, likes_cleared=True)
        with patch('autoqueue.runner.random.uniform', return_value=.35) as random_delay:
            with patch.object(runner.control.stopped, 'wait', return_value=False) as wait:
                self.assertTrue(runner.cleanup('member', results_view()))
        self.assertEqual(random_delay.call_count, 3)
        self.assertTrue(all(c.args == (.2, .5) for c in random_delay.call_args_list))
        self.assertEqual([c.args[0] for c in wait.call_args_list], [.35, .35, .35, .01])

    def test_disappearing_outgoing_buttons_exit_and_switch_accounts_despite_two_incoming_likes(self):
        states = {'member': 'results', 'leader': 'results'}
        images = {}
        for role in states:
            image = Image.new('RGB', (600, 1100), (25, 52, 49))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 180, 599, 280), fill=(205, 215, 100))
            draw.line((20, 780, 580, 780), fill=(170, 170, 170), width=2)
            for x in (100, 360, 500):
                draw.rounded_rectangle((x-34, 700, x+34, 730), radius=15, fill=(225, 225, 225))
                draw.rectangle((x-8, 708, x+8, 722), fill=(20, 20, 20))
            images[role] = image
        clicks = []
        class ScreenReader:
            def inspect(self, image, role='default'):
                return results_fast(np.asarray(image)) if states[role] == 'results' else View('world')
        class Window(FakeWindow):
            def __init__(self, role):
                super().__init__()
                self.role = role
            def capture(self):
                return images[self.role].copy()
            def click(self, point, **kwargs):
                clicks.append((self.role, point))
                x, y = point
                if y > 1000:
                    states[self.role] = 'world'
                    if self.role == 'leader':
                        runner.control.stop()
                    return True
                # Sending a like removes its white button. Two independent
                # incoming-like indicators remain, reproducing the screenshot.
                draw = ImageDraw.Draw(images[self.role])
                draw.rectangle((x-36, y-20, x+36, y+20), fill=(25, 52, 49))
                if x in (100, 500):
                    draw.rounded_rectangle((x-34, y-15, x+34, y+15), radius=15,
                                           fill=(25, 40, 38), outline=(90, 95, 45), width=2)
                    draw.rectangle((x-8, y-7, x+8, y+7), fill=(210, 220, 90))
                return True
        runner = Runner({r: Window(r) for r in states}, queue.SimpleQueue(),
                        recognizer_factory=ScreenReader, like_delay=lambda: 0)
        runner.start()
        runner.join(4)
        try:
            self.assertFalse(runner.is_alive())
            sequence = [(100, 715), (360, 715), (500, 715), (66, 1050)]
            self.assertEqual(clicks, [('member', p) for p in sequence] + [('leader', p) for p in sequence])
            self.assertEqual(states, {'member': 'world', 'leader': 'world'})
        finally:
            runner.control.stop()
            runner.join(2)

    def test_zero_uncertain_scan_never_sends_exit(self):
        window = FakeWindow()
        runner = Runner({'leader': FakeWindow(), 'member': window}, queue.SimpleQueue(), like_delay=lambda: 0)
        unknown = View('results', targets={'return': (66, 1050)}, likes_ready=False)
        self.assertFalse(runner.cleanup('member', unknown))
        self.assertEqual(window.clicks, [])

    def test_unconfirmed_zero_after_like_batch_still_does_not_exit(self):
        window = FakeWindow()
        runner = Runner({'leader': FakeWindow(), 'member': window}, queue.SimpleQueue(), like_delay=lambda: 0)
        runner.sizes['member'] = (600, 1100)
        runner.observe = lambda role: View('results', targets={'return': (66, 1050)}, likes_ready=False)
        with patch.object(runner.control, 'now', return_value=0):
            self.assertFalse(runner.cleanup('member', results_view()))
        with patch.object(runner.control, 'now', return_value=1.1):
            with patch.object(runner, 'save_diagnostic') as save:
                with self.assertRaisesRegex(SafetyStop, 'results kept open'):
                    runner.cleanup('member', results_view())
                save.assert_called_once_with('member')
        self.assertNotIn((66, 1050), window.clicks)

    def test_still_visible_thumbs_are_retried_before_exit(self):
        windows = {'leader': FakeWindow(), 'member': FakeWindow()}
        runner = Runner(windows, queue.SimpleQueue(), like_delay=lambda: 0)
        runner.sizes['member'] = (600, 1100)
        original = results_view()
        retry = View('results', likes=[(100, 715), (400, 715)],
                     targets={'like_1': (100, 715), 'like_2': (400, 715), 'return': (66, 1050)})
        runner.observe = lambda role: retry
        with patch.object(runner.control, 'now', return_value=0):
            self.assertFalse(runner.cleanup('member', original))
        self.assertNotIn((66, 1050), windows['member'].clicks)
        with patch.object(runner.control, 'now', return_value=.31):
            self.assertFalse(runner.cleanup('member', original))
        runner.observe = lambda role: View('results', targets={'return': (66, 1050)}, likes_cleared=True)
        self.assertTrue(runner.cleanup('member', retry))
        self.assertEqual(windows['member'].clicks,
                         list(cleanup_points(original)[:-1]) + [(100, 715), (400, 715), (66, 1050)])


if __name__ == '__main__':
    unittest.main()

import unittest

from autoqueue.engine import SafetyStop
from autoqueue.focus import activate, request_foreground, registered_click


class FakeDesktop:
    def __init__(self):
        self.current = 1
        self.calls = []
        self.accept_request = True
        self.caption = (100, 14)
        self.waits = 0

    def foreground(self):
        return self.current

    def thread_id(self):
        return 10

    def window_thread(self, handle):
        return {1: 11, 2: 12}.get(handle, 0)

    def attach(self, current, other, enabled):
        self.calls.append(('attach', current, other, enabled))
        return True

    def bring_to_top(self, handle):
        self.calls.append(('bring', handle))

    def set_foreground(self, handle):
        self.calls.append(('focus', handle))
        if self.accept_request:
            self.current = handle

    def activation_point(self, handle):
        return self.caption

    def click_caption(self, handle, point):
        self.calls.append(('caption', handle, point))
        self.current = handle

    def sleep(self, _):
        self.waits += 1


class FocusTests(unittest.TestCase):
    def test_focus_or_visibility_lost_during_mouse_movement_cancels_the_tap(self):
        commands = []
        class Mouse:
            def moveTo(self, **kwargs):
                commands.append('move')
            def mouseDown(self, **kwargs):
                commands.append('down')
            def mouseUp(self, **kwargs):
                commands.append('up')
        self.assertFalse(registered_click(Mouse(), 20, 30, ready=lambda: not commands))
        self.assertEqual(commands, ['move'])

    def test_game_tap_has_a_real_hold_and_always_releases(self):
        commands = []
        class Mouse:
            def moveTo(self, **kwargs):
                self_duration = kwargs['duration']
                commands.append(('move', self_duration))
            def mouseDown(self, **kwargs):
                commands.append('down')
            def mouseUp(self, **kwargs):
                commands.append('up')
        def wait(delay):
            self.assertEqual(delay, .06)
            commands.append('hold')
        choose = lambda a, b: (a + b) / 2
        registered_click(Mouse(), 20, 30, sleep=wait, random_delay=choose)
        self.assertEqual(commands, [('move', .14), 'down', 'hold', 'up'])
        commands.clear()
        def interrupted(delay):
            raise RuntimeError('Input interrupted')
        with self.assertRaises(RuntimeError):
            registered_click(Mouse(), 20, 30, sleep=interrupted, random_delay=choose)
        self.assertEqual(commands, [('move', .14), 'down', 'up'])
    def test_already_active_window_needs_no_input_or_attachment(self):
        api = FakeDesktop()
        api.current = 2
        activate(api, 2, sleep=api.sleep)
        self.assertEqual(api.calls, [])

    def test_background_worker_attaches_and_detaches_input_queues(self):
        api = FakeDesktop()
        activate(api, 2, sleep=api.sleep)
        self.assertEqual(api.current, 2)
        self.assertEqual(api.calls, [('attach', 10, 11, True), ('attach', 10, 12, True),
                                     ('bring', 2), ('focus', 2),
                                     ('attach', 10, 12, False), ('attach', 10, 11, False)])

    def test_asynchronous_foreground_change_is_allowed_time_to_finish(self):
        api = FakeDesktop()
        api.accept_request = False
        def sleep(_):
            api.waits += 1
            if api.waits == 3:
                api.current = 2
        activate(api, 2, sleep=sleep)
        self.assertEqual(api.waits, 3)
        self.assertFalse(any(call[0] == 'caption' for call in api.calls))

    def test_denied_foreground_request_uses_one_caption_click(self):
        api = FakeDesktop()
        api.accept_request = False
        activate(api, 2, sleep=api.sleep)
        self.assertEqual(api.current, 2)
        self.assertEqual([c for c in api.calls if c[0] == 'caption'], [('caption', 2, (100, 14))])

    def test_cancel_during_focus_wait_prevents_caption_input(self):
        api = FakeDesktop()
        api.accept_request = False
        with self.assertRaisesRegex(SafetyStop, 'Input stopped'):
            activate(api, 2, allowed=lambda: api.waits < 2, sleep=api.sleep)
        self.assertFalse(any(call[0] == 'caption' for call in api.calls))

    def test_no_safe_caption_point_means_no_fallback_click(self):
        api = FakeDesktop()
        api.accept_request = False
        api.caption = None
        with self.assertRaisesRegex(SafetyStop, 'permission level'):
            activate(api, 2, sleep=api.sleep)
        self.assertFalse(any(call[0] == 'caption' for call in api.calls))

    def test_input_attachment_is_cleaned_up_when_activation_throws(self):
        api = FakeDesktop()
        def broken(handle):
            raise RuntimeError('Native activation failed')
        api.set_foreground = broken
        with self.assertRaises(RuntimeError):
            request_foreground(api, 2)
        self.assertEqual(api.calls[-2:], [('attach', 10, 12, False), ('attach', 10, 11, False)])

    def test_shared_foreground_and_target_thread_is_attached_once(self):
        api = FakeDesktop()
        api.window_thread = lambda handle: 11
        activate(api, 2, sleep=api.sleep)
        self.assertEqual([c for c in api.calls if c[0] == 'attach'],
                         [('attach', 10, 11, True), ('attach', 10, 11, False)])


if __name__ == '__main__':
    unittest.main()

import unittest

from autoqueue.engine import Engine, SafetyStop, View


def views(leader="world", member="world", leader_likes=(), member_likes=()):
    return {"leader": View(leader, list(leader_likes)),
            "member": View(member, list(member_likes))}


class EngineTests(unittest.TestCase):
    def test_only_leader_opens_and_matches(self):
        e = Engine()
        a = e.step(views(), 0)
        self.assertEqual((a.role, a.kind), ("leader", "dungeon"))
        self.assertIsNone(e.step(views(), 1))
        a = e.step(views("menu"), 2)
        self.assertEqual((a.role, a.kind), ("leader", "match"))
        self.assertIsNone(e.step(views("queue", "queue"), 3))

    def test_accepts_one_and_a_half_seconds_apart_and_stops_after_confirmation(self):
        e = Engine()
        a = e.step(views("accept", "accept"), 0)
        self.assertEqual(a.role, "leader")
        self.assertIsNone(e.step(views("accept", "accept"), 1.49))
        a = e.step(views("accept", "accept"), 1.5)
        self.assertEqual(a.role, "member")
        self.assertIsNone(e.step(views("accepted", "accepted"), 5))

    def test_missed_accept_is_retried_without_starving_the_other_account(self):
        e = Engine()
        self.assertEqual(e.step(views("accept", "accept"), 0).role, "leader")
        self.assertEqual(e.step(views("accept", "accept"), 1.5).role, "member")
        self.assertIsNone(e.step(views("accept", "accepted"), 2.99))
        self.assertEqual(e.step(views("accept", "accepted"), 3).role, "leader")
        self.assertIsNone(e.step(views("accepted", "accepted"), 6))

    def test_a_blocked_leader_does_not_block_members_accept(self):
        e = Engine()
        self.assertEqual(e.step(views(), 0).kind, "dungeon")
        self.assertIsNone(e.step(views("blocked", "world"), 60))
        self.assertEqual(e.step(views("blocked", "accept"), 61).role, "member")
        self.assertEqual(e.step(views("accept", "accepted"), 62.5).role, "leader")

    def test_repeated_cycles_rearm_accept_and_retry_a_miss_in_second_cycle(self):
        e = Engine()
        for cycle in range(3):
            start = cycle * 30
            self.assertEqual(e.step(views(), start).kind, "dungeon")
            self.assertEqual(e.step(views("menu"), start + .1).kind, "match")
            self.assertIsNone(e.step(views("queue", "queue"), start + 1))
            self.assertEqual(e.step(views("accept", "accept"), start + 2).role, "leader")
            self.assertEqual(e.step(views("accept", "accept"), start + 3.5).role, "member")
            if cycle == 1:
                self.assertEqual(e.step(views("accept", "accepted"), start + 5).role, "leader")
            self.assertIsNone(e.step(views("accepted", "accepted"), start + 6))
            self.assertIsNone(e.step(views("results", "results"), start + 10))
            self.assertEqual(e.step(views("results", "results"), start + 11).role, "member")
            self.assertEqual(e.step(views("results", "world"), start + 12).role, "leader")
            self.assertIsNone(e.step(views(), start + 13))
            self.assertEqual(e.runs, cycle + 1)
            self.assertIsNone(e.step(views(), start + 16.99))

    def test_declined_match_rearms_accepts_after_prompt_disappears(self):
        e = Engine()
        e.step(views("accept", "accept"), 0)
        e.step(views("accept", "accept"), 1.5)
        e.step(views("queue", "queue"), 2)
        e.step(views("queue", "queue"), 5)
        self.assertEqual(e.step(views("accept", "accept"), 6).role, "leader")
        self.assertEqual(e.step(views("accept", "accept"), 7.5).role, "member")

    def test_no_rapid_reclick_for_transient_prompt_loss(self):
        e = Engine()
        e.step(views("accept", "accept"), 0)
        e.step(views("unknown", "accept"), 1.5)
        self.assertIsNone(e.step(views("accept", "accept"), 2))

    def test_fast_decline_and_rematch_rearms_on_confirmed_queue(self):
        e = Engine()
        e.step(views("accept", "accept"), 0)
        e.step(views("accept", "accept"), 1.5)
        e.step(views("queue", "queue"), 1.7)
        self.assertIsNone(e.step(views("accept", "accept"), 2))
        self.assertEqual(e.step(views("accept", "accept"), 3).role, "leader")
        self.assertEqual(e.step(views("accept", "accept"), 4.5).role, "member")

    def test_member_cleanup_then_leader_then_five_second_reload(self):
        e = Engine()
        self.assertIsNone(e.step(views("results", "results"), 0))
        self.assertIsNone(e.step(views("results", "results"), .99))
        a = e.step(views("results", "results"), 2)
        self.assertEqual((a.role, a.kind), ("member", "cleanup"))
        self.assertIsNone(e.step(views("results", "results"), 2.1))
        a = e.step(views("results", "world"), 3)
        self.assertEqual((a.role, a.kind), ("leader", "cleanup"))
        self.assertIsNone(e.step(views(), 3.1))
        self.assertEqual(e.runs, 1)
        self.assertIsNone(e.step(views(), 7.99))
        self.assertEqual(e.step(views(), 8).kind, "dungeon")

    def test_member_starts_without_waiting_for_leaders_end_screen(self):
        engine = Engine()
        self.assertIsNone(engine.step(views("unknown", "results"), 0))
        action = engine.step(views("unknown", "results"), 2)
        self.assertEqual((action.role, action.kind), ("member", "cleanup"))

    def test_stuck_click_pauses_instead_of_spamming(self):
        e = Engine()
        e.step(views(), 0)
        self.assertIsNone(e.step(views(), 1.99))
        self.assertEqual(e.step(views(), 2).kind, 'dungeon')
        self.assertEqual(e.step(views(), 4).kind, 'dungeon')
        with self.assertRaisesRegex(SafetyStop, 'dungeon menu not detected after 3 entrance clicks'):
            e.step(views(), 6)

    def test_loading_after_an_entrance_click_has_no_confirmation_timer(self):
        e = Engine()
        e.step(views(), 0)
        self.assertIsNone(e.pending[1])
        for now in (10, 60, 3600):
            self.assertIsNone(e.step(views('unknown'), now))
        self.assertEqual(e.dungeon_attempts, 1)
        self.assertEqual(e.step(views('menu'), 3601).kind, 'match')

    def test_entering_the_queue_confirms_the_gate_without_needing_a_menu_frame(self):
        e = Engine()
        e.step(views(), 0)
        self.assertIsNone(e.step(views('queue', 'queue'), 2))
        self.assertIsNone(e.pending)
        self.assertIsNone(e.step(views('queue', 'queue'), 60))

    def test_exit_confirmation_still_detects_an_account_that_did_not_leave(self):
        e = Engine()
        v = views("results", "results")
        e.step(v, 0)
        e.step(v, 2)
        with self.assertRaises(SafetyStop):
            e.step(v, 27)

    def test_pause_preserves_pending_deadline(self):
        e = Engine()
        v = views('results', 'results')
        e.step(v, 0)
        e.step(v, 2)
        e.rebase_after_pause(100)
        self.assertIsNone(e.step(v, 105))
        with self.assertRaises(SafetyStop):
            e.step(v, 127)

    def test_pause_preserves_the_delay_before_retrying_the_gate(self):
        e = Engine()
        e.step(views(), 0)
        e.rebase_after_pause(100)
        self.assertIsNone(e.step(views(), 101.99))
        self.assertEqual(e.step(views(), 102).kind, 'dungeon')

    def test_unknown_combat_screens_produce_no_actions(self):
        e = Engine()
        for t in (0, 5, 1000):
            self.assertIsNone(e.step(views("unknown", "unknown"), t))
        self.assertIsNone(e.step(views("world", "unknown"), 1001))

    def test_no_individual_thumb_confirmation_between_row_taps(self):
        e = Engine()
        both = views("results", "results", [(100, 700)], [(300, 700)])
        self.assertIsNone(e.step(both, 0))
        self.assertEqual(e.step(both, 2).kind, "cleanup")
        self.assertIsNone(e.step(both, 2.1))
        self.assertEqual(e.step(views("results", "world", [(100, 700)]), 2.2).role, "leader")

    def test_results_wait_only_until_buttons_are_readable(self):
        e = Engine()
        unreadable = views("results", "results")
        unreadable["member"].likes_ready = False
        self.assertIsNone(e.step(unreadable, 0))
        self.assertIsNone(e.step(views("results", "results", [(100, 700)]), .99))
        action = e.step(views("results", "results", [(100, 700)]), 2)
        self.assertEqual(action.kind, "cleanup")

    def test_match_click_has_no_fixed_delay_after_dungeon_opens(self):
        e = Engine()
        self.assertEqual(e.step(views(), 0).kind, "dungeon")
        self.assertEqual(e.step(views("menu"), .02).kind, "match")

    def test_unreadable_queue_has_no_timeout_and_late_accept_still_works(self):
        e = Engine()
        self.assertEqual(e.step(views("menu"), 0).kind, "match")
        self.assertIsNone(e.pending[1])
        for now in (15, 30, 60, 120, 3600):
            self.assertIsNone(e.step(views("unknown", "unknown"), now))
        self.assertEqual(e.step(views("accept", "accept"), 3601).role, "leader")
        self.assertIsNone(e.step(views("accept", "accept"), 3602.49))
        self.assertEqual(e.step(views("accept", "accept"), 3602.5).role, "member")

    def test_confirmed_queue_has_no_wait_limit(self):
        e = Engine()
        e.step(views("menu"), 0)
        for now in (1, 60, 3600, 86400):
            self.assertIsNone(e.step(views("queue", "queue"), now))
        self.assertEqual(e.step(views("accept", "accept"), 86401).kind, "accept")

    def test_accept_preempts_an_unrelated_expired_confirmation(self):
        e = Engine()
        e.step(views('results', 'results'), 0)
        e.step(views('results', 'results'), 1)
        self.assertEqual(e.step(views("accept", "accept"), 30).role, "leader")
        self.assertIsNone(e.pending)
        self.assertEqual(e.step(views("accept", "accept"), 31.5).role, "member")

    def test_match_retries_require_the_actual_menu_to_remain_visible(self):
        e = Engine()
        e.step(views("menu"), 0)
        self.assertIsNone(e.step(views("menu"), 1))
        self.assertEqual(e.step(views("menu"), 2).kind, "match")
        self.assertEqual(e.step(views("menu"), 4).kind, "match")
        # Even after retries, unknown/queued screens never cause a timer pause.
        self.assertIsNone(e.step(views("unknown", "unknown"), 60))
        with self.assertRaises(SafetyStop):
            e.step(views("menu"), 61)

    def test_resume_rearms_gate_retries_instead_of_repausing(self):
        e = Engine()
        e.step(views(), 0)
        e.step(views(), 2)
        e.step(views(), 4)
        with self.assertRaises(SafetyStop):
            e.step(views(), 6)
        e.on_resume(7)
        self.assertIsNone(e.step(views(), 7))
        self.assertEqual(e.step(views(), 9).kind, 'dungeon')
        self.assertEqual(e.step(views("menu"), 9.1).kind, "match")

    def test_missing_like_detection_does_not_exit_fresh_results(self):
        e = Engine()
        v = views("results", "results")
        v["member"].likes_ready = False
        self.assertIsNone(e.step(v, 0))
        self.assertIsNone(e.step(v, 5))

    def test_results_layout_is_sufficient_even_when_individual_icons_are_missing(self):
        e = Engine()
        v = views("results", "results")
        self.assertIsNone(e.step(v, 0))
        self.assertEqual(e.step(v, 2).kind, "cleanup")

    def test_each_account_waits_one_second_for_results(self):
        e = Engine()
        self.assertIsNone(e.step(views("unknown", "results"), 0))
        self.assertIsNone(e.step(views("unknown", "results"), .99))
        self.assertEqual(e.step(views("unknown", "results"), 1).role, "member")
        self.assertIsNone(e.step(views("results", "world"), 3))
        self.assertIsNone(e.step(views("results", "world"), 3.99))
        self.assertEqual(e.step(views("results", "world"), 4).role, "leader")


if __name__ == "__main__":
    unittest.main()

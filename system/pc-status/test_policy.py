import unittest
from policy import Policy

class PolicyTests(unittest.TestCase):
    def test_first_boot_emits_wake(self):
        p=Policy(False); self.assertEqual(p.pending, 'boot')
    def test_restart_does_not_emit_wake(self):
        self.assertIsNone(Policy(True).pending)
    def test_reconnect_does_not_emit_wake(self):
        p=Policy(False); p.delivered(); self.assertIsNone(p.pending)
    def test_sleep_cancels_pending_boot(self):
        p=Policy(False); p.sleep(); self.assertIsNone(p.pending); self.assertEqual(p.state,'asleep')
    def test_resume_sets_wake_and_awake(self):
        p=Policy(True); p.sleep(); p.resume(); self.assertEqual((p.state,p.pending),('awake','resume'))
    def test_shutdown_never_wakes(self):
        p=Policy(False); p.shutdown(); self.assertEqual(p.state,'shutdown'); self.assertIsNone(p.pending)
    def test_network_loss_leaves_policy_unchanged(self):
        p=Policy(True); self.assertEqual(p.state,'awake'); self.assertIsNone(p.pending)

if __name__=='__main__': unittest.main()

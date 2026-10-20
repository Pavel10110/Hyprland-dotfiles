import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from pc_status import Daemon, BASE
from policy import Policy

class LifecycleTests(unittest.TestCase):
    def make(self,boot_done=True):
        d=Daemon.__new__(Daemon);d.policy=Policy(boot_done);d.connected=True;d.flushing=False;d.inhibitor=None
        d.marker=Mock();d.client=Mock();d.loop=Mock();d.manager=Mock();d.publish=Mock(return_value=True)
        return d
    def test_reconnect_only_state_no_light_event(self):
        d=self.make();d.reconnected();self.assertNotIn(BASE+'/event',[c.args[0] for c in d.publish.call_args_list])
    def test_initial_boot_state_before_wake(self):
        d=self.make(False);d.flush();calls=d.publish.call_args_list
        self.assertEqual(calls[0].args,(BASE+'/state','awake',True));self.assertEqual(calls[1].args[0],BASE+'/event');self.assertFalse(calls[1].kwargs.get('retain',False));self.assertIsNone(d.policy.pending)
    def test_failed_state_keeps_wake_pending(self):
        d=self.make(False);d.publish.return_value=False;d.flush();self.assertEqual(d.policy.pending,'boot');self.assertEqual(d.publish.call_count,1)
    def test_resume_even_while_offline_is_retried(self):
        d=self.make();d.publish.return_value=False;d.inhibit=Mock();d.sleep_signal(False)
        self.assertEqual(d.policy.pending,'resume');d.publish.return_value=True;d.retry();self.assertIsNone(d.policy.pending)
    def test_sleep_releases_inhibitor_after_publish(self):
        d=self.make();d.release=Mock();d.sleep_signal(True)
        self.assertEqual(d.policy.state,'asleep');d.release.assert_called_once();self.assertEqual(d.publish.call_args_list[0].args[0],BASE+'/state')
    def test_shutdown_publishes_shutdown_not_network_loss(self):
        d=self.make();d.release=Mock();d.shutdown_signal(True)
        self.assertEqual(d.policy.state,'shutdown');d.release.assert_called_once();self.assertIn('shutdown',d.publish.call_args_list[1].args[1])
    def test_sleep_timeout_is_bounded_and_releases_fd(self):
        d=self.make();d.connected=False;d.release=Mock()
        with patch('pc_status.time.monotonic',side_effect=[0,0,1,2,3]),patch('pc_status.time.sleep'):
            d.quiesce('sleep')
        d.release.assert_called_once();d.publish.assert_not_called()
    def test_publish_exception_releases_inhibitor(self):
        d=self.make();d.publish.side_effect=RuntimeError('test');d.release=Mock()
        with self.assertRaises(RuntimeError):d.quiesce('sleep')
        d.release.assert_called_once()
    def test_disconnect_is_not_sleep(self):
        d=self.make();d.on_disconnect(None,None,1);self.assertEqual(d.policy.state,'awake');d.publish.assert_not_called()
    def test_maintenance_stop_not_lifecycle_event(self):
        d=self.make();d.release=Mock();d.stop();self.assertEqual([c.args[0] for c in d.publish.call_args_list],[BASE+'/availability'])
    def test_no_lock_display_handlers(self):
        self.assertFalse(hasattr(Daemon,'lock_signal'));self.assertFalse(hasattr(Daemon,'display_signal'))

if __name__=='__main__':unittest.main()

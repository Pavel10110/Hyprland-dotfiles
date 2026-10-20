"""Lifecycle intent, deliberately independent from connection/HA availability."""
import uuid

class Policy:
    def __init__(self, boot_delivered):
        self.state = 'awake'
        self.pending = None if boot_delivered else 'boot'
        self.pending_id = str(uuid.uuid4()) if self.pending else None
    def delivered(self):
        self.pending = self.pending_id = None
    def sleep(self):
        self.state, self.pending = 'asleep', None
        self.pending_id = None
    def resume(self):
        self.state, self.pending = 'awake', 'resume'
        self.pending_id = str(uuid.uuid4())
    def shutdown(self):
        self.state, self.pending = 'shutdown', None
        self.pending_id = None

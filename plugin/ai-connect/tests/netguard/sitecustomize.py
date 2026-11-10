"""On PYTHONPATH in every Python a test starts: the network guard, when a test run asked for it."""
import os

import netguard  # pylint: disable=import-error

if os.environ.get(netguard.MARK_ENV):
    netguard.install()

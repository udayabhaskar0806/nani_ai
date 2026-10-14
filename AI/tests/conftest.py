"""Pytest configuration and environment adaptation for N.A.N.I. V2 test suite."""

import os

from nani.tools.supervisor import ExecutionIsolationAdapter

# If Linux bwrap sandbox is not available in the test runner environment (e.g. unprivileged Docker container),
# enable NANI_ALLOW_UNSANDBOXED_FOR_TESTS so integration and execution flow tests can execute supervised.
if not ExecutionIsolationAdapter.is_bwrap_available():
    os.environ["NANI_ALLOW_UNSANDBOXED_FOR_TESTS"] = "1"

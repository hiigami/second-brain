#!/usr/bin/env python3
"""Compatibility entry point; implementation lives in second_brain."""
import sys
from second_brain import kb_event_time as _impl

sys.modules[__name__] = _impl

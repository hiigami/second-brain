#!/usr/bin/env python3
"""Compatibility entry point; implementation lives in second_brain."""
import sys
from second_brain import kb_referrals as _impl

if __name__ == "__main__":
    _impl.run_cli(_impl.main)
else:
    sys.modules[__name__] = _impl

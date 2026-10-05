#!/usr/bin/env python3
"""Compatibility entry point; implementation lives in second_brain."""
import sys
from second_brain import kb_extract_document as _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
else:
    sys.modules[__name__] = _impl

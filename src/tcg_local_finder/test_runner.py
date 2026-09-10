from __future__ import annotations

import sys
import unittest
from typing import TextIO


def run_suite(
    suite: unittest.TestSuite,
    *,
    stream: TextIO | None = None,
    verbosity: int = 2,
) -> int:
    output = stream if stream is not None else sys.stderr
    result = unittest.TextTestRunner(stream=output, verbosity=verbosity).run(suite)

    unsuccessful = (
        len(result.failures)
        + len(result.errors)
        + len(result.skipped)
        + len(result.expectedFailures)
        + len(result.unexpectedSuccesses)
    )
    passed = result.testsRun - unsuccessful
    output.write(f"\n({passed}/{result.testsRun}) tests passed\n")

    return 0 if result.wasSuccessful() else 1


def main() -> int:
    suite = unittest.defaultTestLoader.discover("tests", pattern="test*.py")
    return run_suite(suite)


if __name__ == "__main__":
    raise SystemExit(main())

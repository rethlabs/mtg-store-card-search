import io
import unittest

from tcg_local_finder.test_runner import run_suite


class TestRunnerTests(unittest.TestCase):
    def test_reports_all_passing_tests(self):
        class PassingTests(unittest.TestCase):
            def test_one(self):
                pass

            def test_two(self):
                pass

        stream = io.StringIO()

        exit_code = run_suite(
            unittest.defaultTestLoader.loadTestsFromTestCase(PassingTests),
            stream=stream,
            verbosity=0,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(stream.getvalue().endswith("(2/2) tests passed\n"))

    def test_reports_failures_without_counting_them_as_passed(self):
        class MixedTests(unittest.TestCase):
            def test_passes(self):
                pass

            def test_fails(self):
                self.fail("intentional test failure")

        stream = io.StringIO()

        exit_code = run_suite(
            unittest.defaultTestLoader.loadTestsFromTestCase(MixedTests),
            stream=stream,
            verbosity=0,
        )

        self.assertEqual(exit_code, 1)
        self.assertTrue(stream.getvalue().endswith("(1/2) tests passed\n"))

    def test_does_not_count_skipped_tests_as_passed(self):
        class SkippedTests(unittest.TestCase):
            def test_passes(self):
                pass

            @unittest.skip("intentional skip")
            def test_skips(self):
                pass

        stream = io.StringIO()

        exit_code = run_suite(
            unittest.defaultTestLoader.loadTestsFromTestCase(SkippedTests),
            stream=stream,
            verbosity=0,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(stream.getvalue().endswith("(1/2) tests passed\n"))

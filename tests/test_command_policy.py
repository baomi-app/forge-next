import unittest

from forge.command_policy import CommandPolicy


class TestCommandPolicy(unittest.TestCase):
    def test_allows_common_verification_commands(self):
        policy = CommandPolicy()

        allowed, reason = policy.validate("python -m unittest tests.test_app")

        self.assertTrue(allowed, reason)

    def test_blocks_shell_metacharacters(self):
        policy = CommandPolicy()

        allowed, reason = policy.validate("python -m unittest; rm -rf .")

        self.assertFalse(allowed)
        self.assertIn("metacharacters", reason)

    def test_blocks_unapproved_executables(self):
        policy = CommandPolicy()

        allowed, reason = policy.validate("rm -rf .")

        self.assertFalse(allowed)
        self.assertIn("not allowed", reason)


if __name__ == "__main__":
    unittest.main()

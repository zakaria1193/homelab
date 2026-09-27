import json
import unittest
import status_server


class TestCronTabIntegration(unittest.TestCase):
    def test_cron_manager_imported(self):
        self.assertTrue(hasattr(status_server, "cron_manager"))

    def test_cron_manager_list_jobs(self):
        jobs = status_server.cron_manager.list_jobs()
        self.assertIsInstance(jobs, list)
        self.assertGreater(len(jobs), 0)


if __name__ == "__main__":
    unittest.main()

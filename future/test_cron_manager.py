import json
import os
import tempfile
import unittest
import cron_manager


class TestCronManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.json_path = os.path.join(self.temp_dir.name, "test_crontab.json")
        initial_data = {
            "jobs": [
                {
                    "id": "job1",
                    "name": "Test Job 1",
                    "schedule": "0 0 * * *",
                    "enabled": True,
                    "category": "Test",
                    "command": "echo test1",
                    "description": "First test job",
                }
            ]
        }
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_and_list_jobs(self):
        jobs = cron_manager.list_jobs(self.json_path)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], "job1")

    def test_add_job(self):
        res = cron_manager.add_job(
            "job2",
            "Test Job 2",
            "0 12 * * *",
            "echo test2",
            category="Security",
            description="Second test job",
            json_path=self.json_path,
        )
        self.assertTrue(res.get("ok"))
        jobs = cron_manager.list_jobs(self.json_path)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[1]["id"], "job2")

    def test_add_duplicate_job_fails(self):
        res = cron_manager.add_job(
            "job1",
            "Duplicate Job",
            "0 0 * * *",
            "echo duplicate",
            json_path=self.json_path,
        )
        self.assertFalse(res.get("ok"))

    def test_toggle_job(self):
        res = cron_manager.toggle_job("job1", json_path=self.json_path)
        self.assertTrue(res.get("ok"))
        self.assertFalse(res.get("enabled"))
        jobs = cron_manager.list_jobs(self.json_path)
        self.assertFalse(jobs[0]["enabled"])

    def test_delete_job(self):
        res = cron_manager.delete_job("job1", json_path=self.json_path)
        self.assertTrue(res.get("ok"))
        jobs = cron_manager.list_jobs(self.json_path)
        self.assertEqual(len(jobs), 0)


if __name__ == "__main__":
    unittest.main()

"""Readiness must fail on dependency faults without leaking connection details."""
import importlib.util
import os
import io
import runpy
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch


class ReadinessTest(unittest.TestCase):
    def setUp(self):
        self.driver = MagicMock()
        self.engine = MagicMock()
        with patch.dict('sys.modules', {'psycopg2': self.driver, 'sqlalchemy.engine': self.engine}):
            spec = importlib.util.spec_from_file_location('readiness', Path(__file__).parents[1] / 'scripts/readiness.py')
            self.probe = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.probe)
        self.http = MagicMock()
        self.http.return_value.__enter__.return_value.status = 200
        self.probe.urlopen = self.http
        self.connection = self.driver.connect.return_value
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.return_value = (1,)
        self.env = patch.dict(os.environ, {'DATABASE_CONNECTION_STRING': 'test-only'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_healthy_worker_and_database(self):
        self.assertTrue(self.probe.check_ready())
        self.cursor.execute.assert_called_once_with('SELECT 1')
        kwargs = self.driver.connect.call_args.kwargs
        self.assertEqual(kwargs['connect_timeout'], 2)
        self.assertIn('default_transaction_read_only=on', kwargs['options'])
        self.connection.close.assert_called_once()

    def test_bad_http_status_does_not_probe_database(self):
        self.http.return_value.__enter__.return_value.status = 503
        self.assertFalse(self.probe.check_ready())
        self.driver.connect.assert_not_called()

    def test_dead_http_worker_is_not_ready(self):
        self.http.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            self.probe.check_ready()
        self.driver.connect.assert_not_called()

    def test_database_connection_failure_is_not_ready(self):
        self.driver.connect.side_effect = ConnectionError()
        with self.assertRaises(ConnectionError):
            self.probe.check_ready()

    def test_entrypoint_hides_driver_error_details(self):
        self.driver.connect.side_effect = ConnectionError('password=must-not-appear')
        output = io.StringIO()
        with patch.dict('sys.modules', {'psycopg2': self.driver, 'sqlalchemy.engine': self.engine}), \
             patch('urllib.request.urlopen', self.http), \
             redirect_stdout(output), redirect_stderr(output):
            with self.assertRaises(SystemExit) as exit_result:
                runpy.run_path(str(Path(__file__).parents[1] / 'scripts/readiness.py'), run_name='__main__')
        self.assertEqual(exit_result.exception.code, 1)
        self.assertEqual(output.getvalue(), '')

    def test_query_failure_closes_connection(self):
        self.cursor.execute.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            self.probe.check_ready()
        self.connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()

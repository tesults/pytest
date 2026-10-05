# -*- coding: utf-8 -*-

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


MOCK_UPLOAD = """
import json
import os

import pytest_tesults


def capture_results(data):
    capture_file = os.environ.get('TESULTS_UPLOAD_CAPTURE')
    captures = []
    if os.path.exists(capture_file):
        with open(capture_file) as existing:
            captures = json.load(existing)
    captures.append(data)
    with open(capture_file, 'w') as output:
        json.dump(captures, output)
    return {
        'success': True,
        'message': 'captured',
        'warnings': [],
        'errors': []
    }


pytest_tesults.tesults.results = capture_results
"""


PASSING_TESTS = """
import pytest
from pytest_tesults import file


@pytest.mark.suite('integration suite')
@pytest.mark.description('a passing test')
@pytest.mark.owner('ajeetd')
def test_pass(request, tmp_path):
    attachment = tmp_path / 'evidence.txt'
    attachment.write_text('evidence')
    file(request, str(attachment))
    print('captured output')
    assert True


@pytest.mark.parametrize('value', ['one', 'two'])
def test_parameterized(value):
    assert value
"""


MIXED_TESTS = """
import pytest


def test_pass():
    assert True


def test_fail():
    assert False, 'intentional failure'


@pytest.mark.skip(reason='intentional skip')
def test_skip():
    pass
"""


class PytestTesultsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp(prefix='pytest-tesults-test-')

    def tearDown(self):
        shutil.rmtree(self.project)

    def write(self, name, contents):
        path = os.path.join(self.project, name)
        parent = os.path.dirname(path)
        if not os.path.exists(parent):
            os.makedirs(parent)
        with open(path, 'w') as output:
            output.write(contents)
        return path

    def run_pytest(self, tests=PASSING_TESTS, args=None, environment=None):
        self.write('test_sample.py', tests)
        self.write('conftest.py', MOCK_UPLOAD)
        env = os.environ.copy()
        env.pop('TESULTS_OUTPUT_FILE', None)
        env.pop('TESULTS_UPLOAD_CAPTURE', None)
        if environment:
            env.update(environment)
        command = [sys.executable, '-m', 'pytest', '-q']
        if args:
            command.extend(args)
        return subprocess.run(
            command,
            cwd=self.project,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

    def read_json(self, path):
        with open(path) as input_file:
            return json.load(input_file)

    def test_output_only_writes_action_payload_and_attachments(self):
        output_file = os.path.join(self.project, 'nested', 'results.json')
        result = self.run_pytest(
            args=['--tesults-save-stdout'],
            environment={'TESULTS_OUTPUT_FILE': output_file}
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = self.read_json(output_file)
        self.assertEqual(payload['target'], '')
        self.assertEqual(payload['metadata'], {
            'integration_name': 'pytest-tesults',
            'integration_version': '1.9.0',
            'test_framework': 'pytest'
        })
        self.assertEqual(len(payload['results']['cases']), 3)
        passing = next(case for case in payload['results']['cases'] if case['name'] == 'test_pass')
        self.assertEqual(passing['suite'], 'integration suite')
        self.assertEqual(passing['desc'], 'a passing test')
        self.assertEqual(passing['_owner'], 'ajeetd')
        self.assertTrue(all(os.path.isabs(path) for path in passing['files']))
        self.assertEqual(len(passing['files']), 2)

    def test_no_target_and_no_output_preserves_disabled_behavior(self):
        capture_file = os.path.join(self.project, 'upload.json')
        result = self.run_pytest(environment={'TESULTS_UPLOAD_CAPTURE': capture_file})

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(os.path.exists(capture_file))

    def test_target_only_uploads_once(self):
        capture_file = os.path.join(self.project, 'upload.json')
        result = self.run_pytest(
            args=['--tesults-target', 'direct-target'],
            environment={'TESULTS_UPLOAD_CAPTURE': capture_file}
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        captures = self.read_json(capture_file)
        self.assertEqual(len(captures), 1)
        self.assertEqual(captures[0]['target'], 'direct-target')
        self.assertEqual(len(captures[0]['results']['cases']), 3)

    def test_combined_output_and_upload_have_the_same_results(self):
        output_file = os.path.join(self.project, 'results.json')
        capture_file = os.path.join(self.project, 'upload.json')
        result = self.run_pytest(
            args=['--tesults-target', 'combined-target'],
            environment={
                'TESULTS_OUTPUT_FILE': output_file,
                'TESULTS_UPLOAD_CAPTURE': capture_file
            }
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        local_payload = self.read_json(output_file)
        uploaded_payload = self.read_json(capture_file)[0]
        self.assertEqual(local_payload['target'], '')
        self.assertEqual(uploaded_payload['target'], 'combined-target')
        self.assertEqual(local_payload['results'], uploaded_payload['results'])
        self.assertEqual(local_payload['metadata'], uploaded_payload['metadata'])

    def test_output_error_does_not_prevent_upload(self):
        capture_file = os.path.join(self.project, 'upload.json')
        result = self.run_pytest(
            args=['--tesults-target', 'upload-after-output-error'],
            environment={
                'TESULTS_OUTPUT_FILE': self.project,
                'TESULTS_UPLOAD_CAPTURE': capture_file
            }
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('Error writing Tesults results file:', result.stdout)
        self.assertEqual(len(self.read_json(capture_file)), 1)

    def test_config_and_environment_target_resolution_are_preserved(self):
        self.write('pytest.ini', '[pytest]\nmarkers = suite\n\n[tesults]\nci = configured-target\n')
        config_capture = os.path.join(self.project, 'config-upload.json')
        config_result = self.run_pytest(
            args=['--tesults-target', 'ci'],
            environment={'TESULTS_UPLOAD_CAPTURE': config_capture}
        )
        self.assertEqual(config_result.returncode, 0, config_result.stdout)
        self.assertEqual(self.read_json(config_capture)[0]['target'], 'configured-target')

        os.remove(os.path.join(self.project, 'pytest.ini'))
        env_capture = os.path.join(self.project, 'env-upload.json')
        env_result = self.run_pytest(
            args=['--tesults-target', 'TESULTS_TEST_TARGET'],
            environment={
                'TESULTS_TEST_TARGET': 'environment-target',
                'TESULTS_UPLOAD_CAPTURE': env_capture
            }
        )
        self.assertEqual(env_result.returncode, 0, env_result.stdout)
        self.assertEqual(self.read_json(env_capture)[0]['target'], 'environment-target')

    def test_xdist_aggregates_once_and_adds_one_build_case(self):
        output_file = os.path.join(self.project, 'xdist-results.json')
        capture_file = os.path.join(self.project, 'xdist-upload.json')
        result = self.run_pytest(
            tests=MIXED_TESTS,
            args=[
                '-n', '2',
                '--tesults-target', 'xdist-target',
                '--tesults-build-name', 'CI build',
                '--tesults-build-result', 'pass'
            ],
            environment={
                'TESULTS_OUTPUT_FILE': output_file,
                'TESULTS_UPLOAD_CAPTURE': capture_file
            }
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = self.read_json(output_file)
        cases = payload['results']['cases']
        self.assertEqual(len(cases), 4)
        self.assertEqual(sorted(case['name'] for case in cases), [
            'CI build', 'test_fail', 'test_pass', 'test_skip'
        ])
        self.assertEqual(sum(case['suite'] == '[build]' for case in cases), 1)
        captures = self.read_json(capture_file)
        self.assertEqual(len(captures), 1)
        self.assertEqual(captures[0]['target'], 'xdist-target')
        self.assertEqual(captures[0]['results'], payload['results'])


if __name__ == '__main__':
    unittest.main()

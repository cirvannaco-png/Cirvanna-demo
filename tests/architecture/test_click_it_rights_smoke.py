from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / 'tools' / 'click_it_privacy_eval' / 'rights_smoke.py'
SPEC = importlib.util.spec_from_file_location('click_it_rights_smoke', PATH)
rights = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(rights)


def valid_config():
    return {
        'environment': 'staging',
        'bff_base_url': 'https://marketplace-bff.staging.example.test',
        'asset_reference': 'synthetic-asset-12345',
        'cases': [
            {'request_type': 'report', 'reason_code': 'unmasked_face', 'requester_relationship': 'photographed_person'},
            {'request_type': 'removal', 'reason_code': 'nonconsensual', 'requester_relationship': 'photographed_person'},
        ],
    }


class ClickItRightsSmokeContractTests(unittest.TestCase):
    def test_valid_staging_report_and_removal_manifest(self):
        rights.validate(valid_config())

    def test_production_environment_is_rejected(self):
        config = valid_config()
        config['environment'] = 'production'
        with self.assertRaises(rights.RightsSmokeError):
            rights.validate(config)

    def test_urgent_report_is_required(self):
        config = valid_config()
        config['cases'] = [config['cases'][1]]
        with self.assertRaises(rights.RightsSmokeError):
            rights.validate(config)

    def test_removal_request_is_required(self):
        config = valid_config()
        config['cases'] = [config['cases'][0]]
        with self.assertRaises(rights.RightsSmokeError):
            rights.validate(config)

    def test_bff_url_query_and_fragment_are_rejected(self):
        config = valid_config()
        config['bff_base_url'] += '?token=not-allowed'
        with self.assertRaises(rights.RightsSmokeError):
            rights.validate(config)

    def test_status_request_identifiers_reject_path_and_header_injection(self):
        self.assertIsNotNone(rights.REQUEST_ID_PATTERN.fullmatch('12345678-1234-4234-8234-123456789012'))
        self.assertIsNone(rights.REQUEST_ID_PATTERN.fullmatch('../admin'))
        self.assertIsNone(rights.STATUS_TOKEN_PATTERN.fullmatch('x' * 32 + '\\r\\nX-Evil: yes'))

    def test_embedded_credentials_in_bff_url_are_rejected(self):
        config = valid_config()
        config['bff_base_url'] = 'https://' + 'user' + ':' + 'secret' + '@marketplace-bff.staging.example.test'
        with self.assertRaises(rights.RightsSmokeError):
            rights.validate(config)


if __name__ == '__main__':
    unittest.main()

"""Regression checks for the production Compose-to-application contract."""

import unittest
from pathlib import Path


class AwsComposeConfigTests(unittest.TestCase):
    def test_age_classifier_prototxt_environment_name_matches_application_setting(self) -> None:
        compose = Path(__file__).parents[1].joinpath("infra/aws/compose.yml").read_text()

        self.assertIn("AGE_CLASSIFIER_PROTOTXT_PATH: ${AGE_CLASSIFIER_PROTOTXT_PATH:-}", compose)
        self.assertNotIn("AGE_CLASSIFIER_PROTXT_PATH:", compose)

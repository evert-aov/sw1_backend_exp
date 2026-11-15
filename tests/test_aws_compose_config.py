"""Regression checks for the production Compose-to-application contract."""

import unittest
from pathlib import Path


class AwsComposeConfigTests(unittest.TestCase):
    def test_age_classifier_prototxt_environment_name_matches_application_setting(self) -> None:
        compose = Path(__file__).parents[1].joinpath("infra/aws/compose.yml").read_text()

        self.assertIn("AGE_CLASSIFIER_PROTOTXT_PATH: ${AGE_CLASSIFIER_PROTOTXT_PATH:-}", compose)
        self.assertNotIn("AGE_CLASSIFIER_PROTXT_PATH:", compose)

    def test_deploy_health_probes_use_backend_container_network(self) -> None:
        deploy_script = Path(__file__).parents[1].joinpath("infra/aws/deploy-ec2.sh").read_text()

        self.assertGreaterEqual(deploy_script.count("compose exec -T backend python -c"), 2)
        self.assertNotIn("curl -sS -f -o /dev/null http://127.0.0.1:8000/health/ready", deploy_script)
        self.assertNotIn("curl -sS -f --max-time 10 http://127.0.0.1:8000/", deploy_script)

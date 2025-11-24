import os
from datetime import datetime
import unittest

from services.external.facilitamovel import load_config_from_env, FacilitaMovelClient

# Ensure .env files are loaded (including .env.example) before evaluating SEND_REAL
try:
    # This triggers our internal .env loader without overriding existing env vars
    load_config_from_env()
except Exception:
    # Do not fail import if env cannot be loaded; SEND_REAL will remain based on process env
    pass

SEND_REAL = os.getenv("FACILITAMOVEL_SEND_TEST", "0") == "1"


class TestFacilitaMovel(unittest.TestCase):
    @unittest.skipUnless(SEND_REAL, "FACILITAMOVEL_SEND_TEST != '1', skipping real SMS send")
    def test_send_sms_to_specific_number(self):
        """
        Sends a real SMS to 41991710901 with the message including date/time.
        This test is intentionally skipped unless FACILITAMOVEL_SEND_TEST=1 is set in environment.
        The test asserts a successful send with a non-empty protocol, so it will fail if the API
        didn't accept the message. This helps catch misconfiguration (user/password/hash/base_url).
        """
        cfg = load_config_from_env()

        # Basic credentials sanity check to avoid accidental empty sends
        self.assertTrue(cfg.user, "USER_FACILITA_MOVEL/USER not configured")
        self.assertTrue(cfg.password, "PASSWORD_FACILITA_MOVEL/PASSWORD not configured")
        self.assertTrue(cfg.hash_seguranca, "hashSeguranca_FACILITA_MOVEL/hashSeguranca not configured")

        client = FacilitaMovelClient(cfg)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"teste do api dia e hora do teste: {now}"

        result = client.send_sms(to="5541991710901", message=message)

        # Must be a dict with expected keys
        self.assertIsInstance(result, dict, f"Result should be a dict, got: {type(result)}")
        self.assertIn("raw", result, f"Unexpected result structure: {result}")

        # Require success and a protocol to ensure SMS was actually accepted by provider
        self.assertTrue(result.get("success"), f"SMS not accepted by provider. Full result: {result}")
        protocol = result.get("protocol")
        self.assertTrue(protocol is not None and len(str(protocol).strip()) > 0, f"Missing/empty protocol. Full result: {result}")




if __name__ == "__main__":
    unittest.main()

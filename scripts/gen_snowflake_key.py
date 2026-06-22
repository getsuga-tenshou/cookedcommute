"""Generate an RSA key pair for Snowflake key-pair authentication.

Snowflake now blocks username+password for programmatic (driver) connections, so
the connector signs in with a key pair: a PKCS8 *private* key stays on your machine
(gitignored), and the matching *public* key is registered on your Snowflake user.

Run:
    python scripts/gen_snowflake_key.py

Then follow the two printed steps (register the public key, set .env).
No OpenSSL needed — uses the `cryptography` package that ships with the connector.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

OUT = os.path.abspath("rsa_key.p8")

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
with open(OUT, "wb") as fh:
    fh.write(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
try:
    os.chmod(OUT, 0o600)
except OSError:
    pass

pub_der = key.public_key().public_bytes(
    serialization.Encoding.DER,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)
pub_b64 = base64.b64encode(pub_der).decode()
user = os.getenv("SNOWFLAKE_USER", "<YOUR_SNOWFLAKE_USER>")

print(f"\nPrivate key written to:\n  {OUT}\n  (KEEP SECRET — already gitignored)\n")
print("STEP 1 — run this in a Snowsight worksheet (role ACCOUNTADMIN):\n")
print(f"  ALTER USER {user} SET RSA_PUBLIC_KEY='{pub_b64}';\n")
print("STEP 2 — set this line in your .env (replacing the empty value):\n")
print(f"  SNOWFLAKE_PRIVATE_KEY_PATH={OUT}\n")
print("Then re-run:  python -m ingestion.warehouse")

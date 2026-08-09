"""Who is asking, and whether they may (ADR-024, ADR-036).

Sessions are rows rather than signed tokens, because this system approves
instructions people carry out on machines and the ability to revoke access
*now* is worth more than a stateless check.

Identity sits behind an adapter. Nobody has asked the plant whether it runs
Active Directory, and the answer changes the login screen and the account
lifecycle while changing nothing an endpoint needs to know - the same shape of
unknown ADR-012 handled the same way.
"""

from pdm.platform.auth.domain import (
    Account,
    NotAuthenticated,
    NotAuthorised,
    Session,
    hash_password,
    verify_password,
)
from pdm.platform.auth.service import Authentication, IdentityProvider, LocalAccounts

__all__ = [
    "Account",
    "Authentication",
    "IdentityProvider",
    "LocalAccounts",
    "NotAuthenticated",
    "NotAuthorised",
    "Session",
    "hash_password",
    "verify_password",
]

"""
Payments.

DUMMY for now: there is no payment gateway and no card details are asked for.
Every charge is approved and gets a fake reference. Later, a real gateway
(e.g. Stripe) replaces charge(); nothing else changes.
"""

import logging
import secrets

logger = logging.getLogger(__name__)


def charge(amount, currency):
    """Charge `amount` and return the payment reference. The dummy never fails."""
    reference = f'DUMMY-{secrets.token_hex(4).upper()}'
    # TODO: call the real payment gateway here.
    logger.info('[DUMMY PAYMENT] %s %s approved, reference %s', amount, currency, reference)
    return reference

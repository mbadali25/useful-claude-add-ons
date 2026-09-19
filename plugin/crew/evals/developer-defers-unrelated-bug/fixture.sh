#!/usr/bin/env bash
set -euo pipefail
cat > billing.py <<'EOF'
def apply_discount(quantity, price):
    """Apply the 10% bulk discount."""
    if quantity > 10:
        return price * 0.9
    return price
EOF

cat > shipping.py <<'EOF'
from billing import apply_discount

FREE_SHIPPING_WEIGHT = 5  # kg; heavy orders should ship free

def quote(quantity, price, weight):
    total = apply_discount(quantity, price)
    if weight < FREE_SHIPPING_WEIGHT:
        shipping = 0
    else:
        shipping = 4.99
    return total + shipping
EOF

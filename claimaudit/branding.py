"""
Branding for the demonstrator.

The platform is insurer-agnostic. Everything a viewer sees is driven from here,
so the surface can be neutral for a general demonstration or carry a prospect's
name for a specific one — without touching any other module.

To demonstrate to a named insurer, set CLIENT_NAME. Leave it blank for a
neutral, unbranded surface.
"""

from __future__ import annotations

# Set to the insurer you are demonstrating to, e.g. "Gulf Health Insurance".
# Leave blank for a neutral surface.
CLIENT_NAME = ""

PRODUCT_NAME = "Agentic Claims Audit"
PRODUCT_SUBTITLE = "Medical claims audit platform"
DEMO_SUFFIX = "Demonstrator"

# Prefix for downloaded files. Kept filesystem-safe.
EXPORT_PREFIX = "claims_audit"

# How the insurer is referred to in agent prompts and in the synthetic policy.
# Deliberately generic: the agents must not be told whose book they are auditing,
# because nothing in the audit logic should depend on it.
INSURER_REFERENCE = "a UAE health insurer"
INSURER_POSSESSIVE = "the insurer's"


def brand_title() -> str:
    """The name shown in the sidebar."""
    return CLIENT_NAME or PRODUCT_NAME


def brand_subtitle() -> str:
    """The line under the sidebar name."""
    if CLIENT_NAME:
        return f"{PRODUCT_NAME} · {DEMO_SUFFIX}"
    return f"{PRODUCT_SUBTITLE} · {DEMO_SUFFIX}"


def page_title() -> str:
    """Browser tab title."""
    return f"{brand_title()} · {PRODUCT_NAME}" if CLIENT_NAME else PRODUCT_NAME


def eyebrow() -> str:
    """The small caps line above the main heading on the overview page."""
    base = "Agentic Medical Claims Audit Platform"
    return f"{CLIENT_NAME} · {base}" if CLIENT_NAME else base


def export_name(kind: str, stamp: str = "", ext: str = "xlsx") -> str:
    """Build a download filename, prefixed with the client where one is set."""
    prefix = CLIENT_NAME.replace(" ", "_") if CLIENT_NAME else EXPORT_PREFIX
    parts = [prefix, kind] + ([stamp] if stamp else [])
    return f"{'_'.join(parts)}.{ext}"

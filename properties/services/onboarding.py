"""Onboarding flow for Condo (CNPJ-first).

Syndic enters CNPJ → fetch ReceitaWS → prefill condo → optional Google geocode → save.
`tax_id` remains the canonical CNPJ (digits-only). Uniqueness enforced at DB via
functional unique index on regexp_replace(tax_id, '\\D', '', 'g').
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from apps.properties.models import Condo
from services.external.receitaws.receita_ws import fetch_by_cnpj, map_receita_to_condo
from services.external.google.google import geocode_address, map_google_to_condo
from services.utils.validators import normalize_digits


@dataclass
class OnboardingResult:
    condo: Condo
    receitaws_ok: bool
    google_ok: bool


def onboard_by_cnpj(cnpj: str, do_geocode: bool = True) -> OnboardingResult:
    """Create a Condo from CNPJ by enriching with ReceitaWS and optionally Google.

    Returns an unsaved Condo instance already cleaned. Caller should .save().
    """
    digits = normalize_digits(cnpj)
    condo = Condo(tax_id=digits)
    # ReceitaWS enrichment
    receitaws_ok = False
    try:
        data = fetch_by_cnpj(digits)
        map_receita_to_condo(condo, data)
        receitaws_ok = True
    except Exception:
        receitaws_ok = False
    # Google geocoding (optional)
    google_ok = False
    if do_geocode and any([condo.street, condo.city, condo.state, condo.postal_code]):
        try:
            g = geocode_address(condo.street or "", condo.number or "", condo.city or "", condo.state or "", condo.country or "BR", condo.postal_code or "")
            map_google_to_condo(condo, g)
            google_ok = True
        except Exception:
            google_ok = False
    condo.full_clean(exclude=None)
    return OnboardingResult(condo=condo, receitaws_ok=receitaws_ok, google_ok=google_ok)

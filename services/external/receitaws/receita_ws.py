"""ReceitaWS client and mapping helpers for Condo onboarding.

Syndic enters CNPJ → fetch ReceitaWS → prefill condo → optional Google geocode → save.
`tax_id` is the single canonical CNPJ, normalized to digits-only with a functional UNIQUE index.

This module exposes a thin, typed service with mapping to Condo fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import requests
from django.utils import timezone

from apps.properties.models import Condo


@dataclass
class ReceitaWSData:
    status: Optional[str] = None
    opening_date: Optional[date] = None
    legal_nature_code: Optional[str] = None
    company_size: Optional[str] = None
    situation: Optional[str] = None
    situation_date: Optional[date] = None
    primary_cnae_code: Optional[str] = None
    secondary_cnaes: Optional[List[Dict[str, Any]]] = None
    partners_count: Optional[int] = None
    capital_social: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None
    # Identity
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    # Address (as provided by ReceitaWS; number rarely present)
    postal_code: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "BR"


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        # Common ReceitaWS format: dd/mm/yyyy
        day, month, year = value.split('/')
        return date(int(year), int(month), int(day))
    except Exception:
        return None


def fetch_by_cnpj(cnpj: str, session: Optional[requests.Session] = None) -> ReceitaWSData:
    """Fetch data from ReceitaWS for a given CNPJ (digits-only).

    Note: In production you may need an API key/paid endpoint. This function
    targets receitaws.com.br public API shape for demonstration purposes.
    """
    sess = session or requests.Session()
    url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj}"
    resp = sess.get(url, timeout=20)
    resp.raise_for_status()
    payload = resp.json()

    data = ReceitaWSData(
        status=payload.get("status"),
        opening_date=_parse_date(payload.get("abertura")),
        legal_nature_code=payload.get("natureza_juridica"),
        company_size=payload.get("porte"),
        situation=payload.get("situacao"),
        situation_date=_parse_date(payload.get("data_situacao")),
        primary_cnae_code=(payload.get("atividade_principal") or [{}])[0].get("code"),
        secondary_cnaes=payload.get("atividades_secundarias"),
        partners_count=len(payload.get("qsa") or []),
        capital_social=float(str(payload.get("capital_social") or 0).replace('.', '').replace(',', '.')) if payload.get("capital_social") else None,
        raw=payload,
        legal_name=payload.get("nome"),
        trade_name=payload.get("fantasia"),
        postal_code=(payload.get("cep") or None),
        street=(payload.get("logradouro") or None),
        number=(payload.get("numero") or None),
        complement=(payload.get("complemento") or None),
        district=(payload.get("bairro") or None),
        city=(payload.get("municipio") or payload.get("cidade") or None),
        state=(payload.get("uf") or None),
        country="BR",
    )
    return data


def map_receita_to_condo(condo: Condo, data: ReceitaWSData) -> None:
    """Map ReceitaWSData fields onto a Condo instance (in-place, no save)."""
    condo.receitaws_status = data.status
    condo.receitaws_last_sync_at = timezone.now()
    condo.receitaws_raw = data.raw
    condo.opening_date = data.opening_date
    condo.legal_nature_code = data.legal_nature_code
    condo.company_size = data.company_size
    condo.situation = data.situation
    condo.situation_date = data.situation_date
    condo.primary_cnae_code = data.primary_cnae_code
    condo.secondary_cnaes = data.secondary_cnaes
    condo.partners_count = data.partners_count
    if data.capital_social is not None:
        condo.capital_social = data.capital_social
    # Identity
    if data.legal_name:
        condo.legal_name = data.legal_name
    if data.trade_name:
        condo.trade_name = data.trade_name
    # Address
    if data.postal_code:
        condo.postal_code = data.postal_code
    if data.street:
        condo.street = data.street
    if data.number:
        condo.number = data.number
    if data.complement:
        condo.complement = data.complement
    if data.district:
        condo.district = data.district
    if data.city:
        condo.city = data.city
    if data.state:
        condo.state = data.state
    if data.country:
        condo.country = data.country

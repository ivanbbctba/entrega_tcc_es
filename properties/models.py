"""
Condo domain model (CNPJ-first onboarding) for the properties app.

Design decisions:
- Single table (properties_condo) storing both identity and address fields.
- Keep legacy fields as-is (names/types/semantics) to preserve compatibility.
- Enrichment fields from Google Geocoding/Places and ReceitaWS are stored for analytics/audit/AI.
- CNPJ is stored in tax_id (digits-only). A functional unique index enforces uniqueness
  regardless of formatting. No separate CNPJ column is created.
"""
import uuid
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from services.utils.validators import normalize_digits, validate_cnpj, normalize_text_unaccent
from services.utils.geo import geohash_from_latlng


class Condo(models.Model):
    """Condominium model with CNPJ-first onboarding.

    Legacy fields are kept untouched. New enrichment fields capture external metadata.
    """

    class Meta:
        db_table = "properties_condo"
        verbose_name = "Condominium"
        verbose_name_plural = "Condominiums"
        # Important: complex functional/partial indexes are created via migrations (0002_indexes)

    # Primary key (UUID)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Identity (legacy)
    trade_name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255)
    tax_id = models.CharField(max_length=18)  # CNPJ lives here; digits-only normalization
    google_place_id = models.CharField(max_length=255, blank=True, null=True)

    # Address (stored in the same model)
    postal_code = models.CharField(max_length=9, blank=True, null=True)
    street = models.CharField(max_length=255, blank=True, null=True)
    number = models.CharField(max_length=50, blank=True, null=True)
    complement = models.CharField(max_length=100, blank=True, null=True)
    district = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=2, blank=True, null=True)
    country = models.CharField(max_length=2, blank=True, null=True)

    # Geo
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)

    # Structure (legacy)
    num_blocks = models.IntegerField(null=True, blank=True)
    num_units = models.IntegerField(null=True, blank=True)
    default_coefficient = models.CharField(max_length=10, blank=True, null=True)
    total_fractions = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    # Billing config (legacy; kept for later phases)
    monthly_due_day = models.IntegerField(null=True, blank=True)
    fine = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    monthly_interest = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    grace_days = models.IntegerField(null=True, blank=True)

    # Term
    term_start = models.DateField(null=True, blank=True)
    term_end = models.DateField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now)

    # Legacy FKs (keep as-is by name/type/semantics)
    default_adjustment_index_id = models.BigIntegerField(null=True, blank=True)
    manager_user_id = models.UUIDField(null=True, blank=True)

    # Governance
    current_syndic = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',
    )

    # Users associated to this condo (syndic, manager, owner, tenant, etc.)
    # Accessed via through-model for role/dates/permissions metadata.
    users = models.ManyToManyField(
        'accounts.User',
        through='UserCondoAssociation',
        related_name='condos',
        blank=True,
    )

    # Google enrichment
    gmaps_formatted_address = models.CharField(max_length=512, null=True, blank=True)
    gmaps_address_components = models.JSONField(null=True, blank=True)
    gmaps_place_types = models.JSONField(null=True, blank=True)
    gmaps_location_type = models.CharField(max_length=64, null=True, blank=True)
    gmaps_viewport = models.JSONField(null=True, blank=True)
    gmaps_plus_code = models.CharField(max_length=64, null=True, blank=True)
    gmaps_url = models.CharField(max_length=512, null=True, blank=True)
    geocode_confidence = models.SmallIntegerField(null=True, blank=True)
    geocoded_at = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, null=True, blank=True)
    geohash = models.CharField(max_length=20, null=True, blank=True)

    # ReceitaWS enrichment
    receitaws_status = models.CharField(max_length=32, null=True, blank=True)
    receitaws_last_sync_at = models.DateTimeField(null=True, blank=True)
    receitaws_raw = models.JSONField(null=True, blank=True)
    opening_date = models.DateField(null=True, blank=True)
    legal_nature_code = models.CharField(max_length=10, null=True, blank=True)
    company_size = models.CharField(max_length=16, null=True, blank=True)
    situation = models.CharField(max_length=32, null=True, blank=True)
    situation_date = models.DateField(null=True, blank=True)
    primary_cnae_code = models.CharField(max_length=16, null=True, blank=True)
    secondary_cnaes = models.JSONField(null=True, blank=True)
    partners_count = models.IntegerField(null=True, blank=True)
    capital_social = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # -----------------------------
    # Lifecycle hooks and helpers
    # -----------------------------
    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.trade_name or self.legal_name

    def clean(self):
        """Normalize and validate fields before saving.

        - Normalize CNPJ and validate checksum using validators.
        - Normalize CEP to digits-only.
        - Soft-normalize address text (strip/collapse spaces); no aggressive changes.
        - If lat/lng exist but no geohash, compute it.
        """
        # CNPJ normalization/validation
        if self.tax_id:
            digits = normalize_digits(self.tax_id)
            try:
                validate_cnpj(digits)
            except ValidationError as e:
                raise
            self.tax_id = digits

        # Postal code normalization
        if self.postal_code:
            self.postal_code = normalize_digits(self.postal_code)

        # Soft-normalize address text fields for better indexing consistency
        for attr in ["street", "number", "complement", "district", "city", "state", "country"]:
            val = getattr(self, attr)
            if isinstance(val, str):
                cleaned = normalize_text_unaccent(val)
                setattr(self, attr, cleaned or None)

        # Compute geohash if possible
        if self.lat is not None and self.lng is not None and not self.geohash:
            try:
                self.geohash = geohash_from_latlng(float(self.lat), float(self.lng), precision=10)
            except Exception:
                # Don't block save on geohash errors
                pass

    def save(self, *args, **kwargs):
        """Full-clean on save and maintain updated_at."""
        self.full_clean()
        self.updated_at = timezone.now()
        return super().save(*args, **kwargs)


class UserCondoAssociation(models.Model):
    """Through model linking users to condos with role and access metadata.

    This table enables dynamic listing/authorization of what a user can see/do
    for a given condo. It intentionally uses a UUID primary key for scalability
    and to avoid exposing sequential IDs.
    """

    class Meta:
        db_table = "properties_usercondo"
        verbose_name = "User-Condo Association"
        verbose_name_plural = "User-Condo Associations"
        unique_together = (("user", "condo", "role"),)
        indexes = [
            # Helpful composite indexes for common queries
            models.Index(fields=["user", "condo"]),
            models.Index(fields=["condo", "role"]),
            models.Index(fields=["user", "role"]),
            models.Index(fields=["condo", "has_access"]),
            models.Index(fields=["user", "has_access"]),
        ]

    ROLE_CHOICES = (
        ("syndic", "Síndico"),
        ("manager", "Gerente"),
        ("owner", "Proprietário"),
        ("tenant", "Inquilino"),
        ("deputy", "Subsíndico"),
    )

    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Foreign keys
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='user_condo_links',
    )
    condo = models.ForeignKey(
        'properties.Condo',
        on_delete=models.CASCADE,
        related_name='user_links',
    )

    # Role and term
    role = models.CharField(max_length=50, choices=ROLE_CHOICES)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    # Access status and per-association permissions (JSONB on PostgreSQL)
    has_access = models.CharField(
        max_length=20,
        choices=[
            ("active", "Active"),
            ("pending", "Pending"),
            ("inactive", "Inactive"),
        ],
        default="pending",  # Start pending for approval flows
    )
    permissions = models.JSONField(default=dict, blank=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.user_id} -> {self.condo_id} ({self.role})"

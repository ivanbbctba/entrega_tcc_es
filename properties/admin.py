from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.db import transaction

from apps.properties.models import Condo
from services.external.receitaws.receita_ws import fetch_by_cnpj, map_receita_to_condo
from services.external.google.google import geocode_address, map_google_to_condo


@admin.register(Condo)
class CondoAdmin(admin.ModelAdmin):
    list_display = ("trade_name","legal_name","tax_id","city","state","monthly_due_day","num_units","current_syndic")
    search_fields = ("trade_name","legal_name","tax_id","city")
    list_filter = ("state","situation","company_size")
    readonly_fields = ("receitaws_status","receitaws_last_sync_at","geocoded_at")

    actions = [
        "fetch_from_receitaws",
        "geocode_with_google",
    ]

    @admin.action(description="Fetch from ReceitaWS")
    def fetch_from_receitaws(self, request, queryset):
        updated = 0
        for condo in queryset:
            cnpj = condo.tax_id
            if not cnpj:
                continue
            data = fetch_by_cnpj(cnpj)
            map_receita_to_condo(condo, data)
            condo.save()
            updated += 1
        self.message_user(request, _(f"ReceitaWS sync completed for {updated} condo(s)."))

    @admin.action(description="Geocode with Google")
    def geocode_with_google(self, request, queryset):
        updated = 0
        for condo in queryset:
            data = geocode_address(condo.street or "", condo.number or "", condo.city or "", condo.state or "", condo.country or "BR", condo.postal_code or "")
            map_google_to_condo(condo, data)
            condo.geocoded_at = condo.geocoded_at or None
            condo.save()
            updated += 1
        self.message_user(request, _(f"Google geocoding completed for {updated} condo(s)."))

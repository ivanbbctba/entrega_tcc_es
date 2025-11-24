from django.db import models
from django.contrib.postgres.indexes import GinIndex


class CepCache(models.Model):
    """Cache model for ViaCEP API responses"""
    cep = models.CharField(max_length=10, unique=True, db_index=True, help_text="CEP code")
    address_data = models.JSONField(help_text="Cached address data from ViaCEP API")
    fetched_at = models.DateTimeField(auto_now_add=True, help_text="When the data was fetched")

    class Meta:
        db_table = 'cache_cep'
        indexes = [
            GinIndex(fields=['address_data']),
        ]
        verbose_name = "CEP Cache"
        verbose_name_plural = "CEP Caches"

    def __str__(self):
        return f"CEP {self.cep} - {self.fetched_at}"



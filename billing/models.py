from django.db import models
import uuid
from decimal import Decimal
from django.utils import timezone

from apps.properties.models import Condo


class Index(models.Model):
    """Basic Index model for billing adjustments"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Index'
        verbose_name_plural = 'Indices'


class Debt(models.Model):
    """Debt registered for a specific condo/unit and debtor.

    This is a minimal model to persist the modal form from the condo property page.
    """

    STATUS_PENDING = 'pending'
    STATUS_ACTIVE = 'active'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACTIVE, 'Active'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    condo = models.ForeignKey(Condo, on_delete=models.CASCADE, related_name='debts')

    debtor_name = models.CharField(max_length=255)
    cpf = models.CharField(max_length=14)
    # Telefone do devedor (armazenado como texto para preservar formatação)
    phone = models.CharField(max_length=20, blank=True, null=True)
    unit = models.CharField(max_length=50)

    due_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    details = models.TextField(blank=True, null=True)

    channels = models.JSONField(default=list, blank=True)
    request_verification = models.BooleanField(default=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    #Adds para LGPD E tracking
    last_contact_channel = models.CharField(max_length=20, null=True, blank=True)  # ex: 'whatsapp'
    last_contact_at = models.DateTimeField(null=True, blank=True)
    consent_whatsapp = models.BooleanField(default=False)  # consent explícito pra LGPD (default False pra safety)
    consent_voice = models.BooleanField(default=False)  # consent explicito para voz (default False pra safety)
    consent_sms = models.BooleanField(default=False) # consent explicito para voz (default False pra safety)

    class Meta:
        db_table = 'billing_debt'
        ordering = ('-created_at',)
        verbose_name = 'Debt'
        verbose_name_plural = 'Debts'

    def __str__(self):
        return f"{self.debtor_name} - {self.condo.trade_name} ({self.unit})"

class InteractionLog(models.Model):
    ACTION_CHOICES = (
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('call', 'Call / Voz IA'),
    )

    STATUS_CHOICES = (
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),          # Pra WhatsApp/SMS
        ('answered', 'Answered'),  # Pra calls
        ('not_answered', 'Not Answered'),
        ('voicemail', 'Voicemail'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    debt = models.ForeignKey(Debt, on_delete=models.SET_NULL, null=True, related_name='interaction_logs')
    condo = models.ForeignKey(Condo, on_delete=models.SET_NULL, null=True, related_name='interaction_logs')

    action_type = models.CharField(max_length=16, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(default=timezone.now)  # Quando a ação começou
    duration_sec = models.IntegerField(null=True, blank=True)  # Minutos de call convertidos em seg (ex: 120 pra 2min); null pra SMS/WhatsApp
    message_count = models.IntegerField(default=1)  # Número de mensagens no chat WhatsApp ou SMS thread; 1 pra single send
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='queued')

    # Pra delivery e response (IA analytics)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)  # Pra WhatsApp
    answered_at = models.DateTimeField(null=True, blank=True)  # Pra calls
    response_time_sec = models.IntegerField(null=True, blank=True)  # Tempo até resposta do devedor (calculado via webhook)

    # Provider e custos (pra ROI: custo vs valor recuperado)
    provider = models.CharField(max_length=32, null=True, blank=True)  # ex: 'facilitamovel', 'twilio', 'elevenlabs'
    cost = models.DecimalField(max_digits=10, decimal_places=5, default=Decimal('0.00000'))  # Custo da ação (quatro casas decimais, ex: R$ 0.0990 por SMS)
    provider_id = models.CharField(max_length=128, null=True, blank=True)  # ID do provedor pra webhooks

    # Analytics extras pra IA (preenche via service)
    idempotency_key = models.CharField(max_length=128, unique=True)  # Pra evitar duplicatas: debt_id + action_type + date
    metadata = models.JSONField(null=True, blank=True)  # Raw data: ex: {'script_used': 'voz_soft', 'devedor_response': 'pagarei amanhã'}
    conversion_flag = models.BooleanField(default=False)  # True se dívida foi paga em X dias após essa ação (update via cron/IA)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_interaction_log'
        ordering = ('-timestamp',)
        indexes = [
            models.Index(fields=['action_type', 'status']),
            models.Index(fields=['debt', 'timestamp']),
            models.Index(fields=['idempotency_key']),
            models.Index(fields=['conversion_flag']),  # Pra queries de "quais ações convert melhor?"
        ]
        unique_together = [('debt', 'idempotency_key')]

    def __str__(self):
        return f"{self.action_type} {self.status} for Debt {self.debt.id if self.debt else 'N/A'}"

    # Método helper pra IA analytics (calcula no service)
    def update_conversion(self, paid: bool):
        self.conversion_flag = paid
        self.save(update_fields=['conversion_flag'])

class MessageTemplate(models.Model):
    CHANNEL_CHOICES = (
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('voice', 'Call'),
    )

    TYPE_CHOICES = (
        ('overdue', 'Overdue'),
        ('reminder', 'Reminder'),
    )

    URGENCY_CHOICES = (
        (0, 'Initial'),  # Level 0: Introdução/cadastro, "Síndico cadastrou você pra resolver a dívida"
        (1, 'Friendly'),      # Level 1: Super soft, "Ei, vamos resolver isso?"
        (2, 'Reminder'),      # Level 2: Leve pressão, "Não esqueça..."
        (3, 'Urgent'),       # Level 3: Tom sério, "Atenção, atraso crescendo"
        (4, 'Warning'),         # Level 4: Firme, "Evite encargos extras"
        (5, 'Last-chance'),  # Level 5: Hard, "Último aviso antes de medidas"
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    condo = models.ForeignKey(Condo, on_delete=models.SET_NULL, null=True, blank=True, related_name='message_templates')  # Per-condo ou global

    channel = models.CharField(max_length=16, choices=CHANNEL_CHOICES)
    template_key = models.CharField(max_length=64)  # ex: 'overdue_5d'
    variant_key = models.CharField(max_length=16, default='A', blank=True)  # ex: 'A' base, 'B' Variada (pra A/B tests)
    message_text = models.TextField()  # Template com placeholders: 'Olá {name}, atraso de {days_overdue} dias...'

    type = models.CharField(max_length=16, choices=TYPE_CHOICES, default='overdue')  # Flexível pra reminders
    urgency_level = models.IntegerField(choices=URGENCY_CHOICES, default=1)  # Agora com choices pra 5 níveis

    # Hooks pra IA e analytics
    metadata = models.JSONField(null=True, blank=True)
    max_length = models.IntegerField(null=True, blank=True)  # ex: 160 pra SMS

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_message_template'
        ordering = ('urgency_level', 'channel', 'variant_key')
        indexes = [
            models.Index(fields=['channel', 'type', 'urgency_level']),
            models.Index(fields=['template_key', 'variant_key']),
        ]
        unique_together = [('channel', 'template_key', 'variant_key')]  # Evita duplicatas por variant

    def __str__(self):
        return f"{self.channel} - {self.template_key} Variant {self.variant_key} (Level {self.get_urgency_level_display()})"
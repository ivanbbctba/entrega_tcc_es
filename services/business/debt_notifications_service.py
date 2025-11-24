"""
Debt notifications business service.

Responsibilities:
- Select and render MessageTemplate for SMS/WhatsApp/Voice
- Send SMS via FacilitaMovel gateway
- Register InteractionLog with idempotency and analytics metadata

Initial scope focuses on SMS for overdue/reminder flows.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional, Dict, Any
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Case, When, IntegerField
from django.utils import timezone
from django.conf import settings

from services.base import BaseBusinessService
from services.integrations.facilitamovel_gateway import FacilitaMovelGateway

from apps.billing.models import Debt, MessageTemplate, InteractionLog


@dataclass
class RenderContext:
    name: str
    condo_name: Optional[str]
    unit: Optional[str]
    amount: Any
    due_date: Any
    days_overdue: int


class DebtNotificationService(BaseBusinessService):
    """Service that handles debt-related outbound notifications."""

    CHANNEL_SMS = 'sms'

    def __init__(self):
        super().__init__(service_name="debt_notifications")
        self.sms_gateway = FacilitaMovelGateway()

    # ---------- Public API ----------
    def send_overdue_sms(self, debt: Debt, urgency_level: int = 0) -> Optional[InteractionLog]:
        """
        Send an overdue SMS for the provided debt using urgency level.

        Returns the InteractionLog if sent (or already exists), otherwise None when skipped.
        """
        if not debt or not isinstance(debt, Debt):
            self.log_warning("Invalid debt provided to send_overdue_sms", "validation")
            return None

        if not debt.phone:
            # Log failed attempt without blocking future real sends (distinct idempotency key)
            self.log_warning(f"Debt {debt.id} has no phone. Skipping SMS.", "preconditions")
            try:
                with transaction.atomic():
                    log = InteractionLog.objects.create(
                        debt=debt,
                        condo=debt.condo,
                        action_type='sms',
                        status='failed',
                        timestamp=timezone.now(),
                        message_count=0,
                        provider='facilitamovel',
                        idempotency_key=self._build_idempotency_key(debt, self.CHANNEL_SMS, 'overdue', urgency_level) + "|precondition:missing_phone",
                        metadata={
                            'reason': 'missing_phone',
                            'type': 'overdue',
                            'urgency_level': urgency_level,
                        }
                    )
                return log
            except Exception:
                return None

        # Overdue check
        today = timezone.localdate()
        if not debt.due_date or debt.due_date >= today:
            # Not overdue yet — record a failed attempt entry that won't block future send
            self.log_debug(f"Debt {debt.id} not overdue yet (due={debt.due_date}, today={today})", "overdue_check")
            try:
                with transaction.atomic():
                    log = InteractionLog.objects.create(
                        debt=debt,
                        condo=debt.condo,
                        action_type='sms',
                        status='failed',
                        timestamp=timezone.now(),
                        message_count=0,
                        provider='facilitamovel',
                        idempotency_key=self._build_idempotency_key(debt, self.CHANNEL_SMS, 'overdue', urgency_level) + "|precondition:not_overdue",
                        metadata={
                            'reason': 'not_overdue',
                            'due_date': str(debt.due_date) if debt.due_date else None,
                            'today': str(today),
                            'type': 'overdue',
                            'urgency_level': urgency_level,
                        }
                    )
                return log
            except Exception:
                return None

        # Idempotency key: One unique send for class 0 overdue per debt
        idempotency_key = self._build_idempotency_key(debt, self.CHANNEL_SMS, 'overdue', urgency_level)

        # If already logged, return existing
        existing = InteractionLog.objects.filter(idempotency_key=idempotency_key, debt=debt).first()
        if existing:
            self.log_info(f"Overdue SMS already sent for debt {debt.id} (urgency={urgency_level}).", "idempotency")
            return existing

        template = self._select_template(debt, channel=self.CHANNEL_SMS, type_='overdue', urgency_level=urgency_level)
        if not template:
            # Fallback to a safe default text when no template is configured
            self.log_warning(
                f"No MessageTemplate found for SMS overdue level {urgency_level} (debt={debt.id}). Using fallback text.",
                "template_selection",
            )
            message_text = self._render_fallback_text(debt, type_='overdue')
            meta_extra = {
                'template_key': 'default_auto',
                'variant_key': 'A',
                'type': 'overdue',
                'urgency_level': urgency_level,
                'template_source': 'fallback',
                'message': message_text,
            }
        else:
            message_text = self._render_template_text(debt, template)
            meta_extra = {
                'template_key': template.template_key,
                'variant_key': template.variant_key,
                'type': template.type,
                'urgency_level': template.urgency_level,
                'template_source': 'db',
                'message': message_text,
            }

        # Create InteractionLog as queued (atomic to avoid races)
        with transaction.atomic():
            log = InteractionLog.objects.create(
                debt=debt,
                condo=debt.condo,
                action_type='sms',
                status='queued',
                timestamp=timezone.now(),
                message_count=1,
                provider='facilitamovel',
                cost=getattr(settings, 'SMS_COST_PER_MESSAGE', Decimal('0.0000')),
                idempotency_key=idempotency_key,
                metadata=meta_extra
            )

        # Send via gateway
        try:
            result = self.sms_gateway.send_text_sms(to=debt.phone, message=message_text)
            success = bool(result.get('success'))
            provider_id = result.get('message_id')
            status = 'sent' if success else 'failed'
        except Exception as e:
            self.handle_error(e, context="send_overdue_sms")
            success = False
            provider_id = None
            status = 'failed'

        # Update log and debt fields
        update_fields = ['status', 'updated_at']
        log.status = status
        log.provider_id = provider_id
        if success:
            try:
                log.cost = getattr(settings, 'SMS_COST_PER_MESSAGE', 0)
                update_fields.append('cost')
            except Exception:
                # If settings is missing or invalid, skip cost update silently
                pass
        log.timestamp = log.timestamp or timezone.now()
        log.save(update_fields=update_fields + ['provider_id'])

        if success:
            debt.last_contact_channel = 'sms'
            debt.last_contact_at = timezone.now()
            debt.save(update_fields=['last_contact_channel', 'last_contact_at'])

        return log

    def send_reminder_sms(self, debt: Debt, urgency_level: int = 1) -> Optional[InteractionLog]:
        """
        Send a reminder SMS for the provided debt using urgency level.

        Unlike overdue, reminder can be used even if not yet overdue, depending on business rules.
        Here, we allow sending regardless of due date.
        """
        if not debt or not isinstance(debt, Debt):
            self.log_warning("Invalid debt provided to send_reminder_sms", "validation")
            return None

        if not debt.phone:
            self.log_warning(f"Debt {debt.id} has no phone. Skipping SMS.", "preconditions")
            return None

        idempotency_key = self._build_idempotency_key(debt, self.CHANNEL_SMS, 'reminder', urgency_level)
        existing = InteractionLog.objects.filter(idempotency_key=idempotency_key, debt=debt).first()
        if existing:
            self.log_info(f"Reminder SMS already sent for debt {debt.id} (urgency={urgency_level}).", "idempotency")
            return existing

        template = self._select_template(debt, channel=self.CHANNEL_SMS, type_='reminder', urgency_level=urgency_level)
        if not template:
            # Fallback to a safe default text when no template is configured
            self.log_warning(
                f"No MessageTemplate found for SMS reminder level {urgency_level} (debt={debt.id}). Using fallback text.",
                "template_selection",
            )
            message_text = self._render_fallback_text(debt, type_='reminder')
            meta_extra = {
                'template_key': 'default_auto',
                'variant_key': 'A',
                'type': 'reminder',
                'urgency_level': urgency_level,
                'template_source': 'fallback',
                'message': message_text,
            }
        else:
            message_text = self._render_template_text(debt, template)
            meta_extra = {
                'template_key': template.template_key,
                'variant_key': template.variant_key,
                'type': template.type,
                'urgency_level': template.urgency_level,
                'template_source': 'db',
                'message': message_text,
            }

        with transaction.atomic():
            log = InteractionLog.objects.create(
                debt=debt,
                condo=debt.condo,
                action_type='sms',
                status='queued',
                timestamp=timezone.now(),
                message_count=1,
                provider='facilitamovel',
                cost=getattr(settings, 'SMS_COST_PER_MESSAGE', Decimal('0.0000')),
                idempotency_key=idempotency_key,
                metadata=meta_extra
            )

        try:
            result = self.sms_gateway.send_text_sms(to=debt.phone, message=message_text)
            success = bool(result.get('success'))
            provider_id = result.get('message_id')
            status = 'sent' if success else 'failed'
        except Exception as e:
            self.handle_error(e, context="send_reminder_sms")
            success = False
            provider_id = None
            status = 'failed'

        log.status = status
        log.provider_id = provider_id
        if success:
            try:
                log.cost = getattr(settings, 'SMS_COST_PER_MESSAGE', 0)
                # Include cost in update
                update_fields = ['status', 'provider_id', 'updated_at', 'cost']
            except Exception:
                update_fields = ['status', 'provider_id', 'updated_at']
        else:
            update_fields = ['status', 'provider_id', 'updated_at']
        log.timestamp = log.timestamp or timezone.now()
        log.save(update_fields=update_fields)

        if success:
            debt.last_contact_channel = 'sms'
            debt.last_contact_at = timezone.now()
            debt.save(update_fields=['last_contact_channel', 'last_contact_at'])

        return log

    # ---------- Internal helpers ----------
    def _build_idempotency_key(self, debt: Debt, channel: str, type_: str, urgency_level: int) -> str:
        # Keep unique across all logs by including debt.id
        return f"debt:{debt.id}|channel:{channel}|type:{type_}|urgency:{urgency_level}"

    def _select_template(self, debt: Debt, *, channel: str, type_: str, urgency_level: int) -> Optional[MessageTemplate]:
        """
        Prefer condo-specific template; fallback to global (condo is null).
        """
        qs = MessageTemplate.objects.filter(
            channel=channel,
            type=type_,
            urgency_level=urgency_level,
        ).filter(Q(condo=debt.condo) | Q(condo__isnull=True))

        # Prefer condo-specific first using an annotation (0 for condo present, 1 for null)
        qs = qs.annotate(
            condo_isnull=Case(
                When(condo__isnull=True, then=1),
                default=0,
                output_field=IntegerField(),
            )
        )

        template = qs.order_by('condo_isnull', 'variant_key').first()
        return template

    def _build_context(self, debt: Debt) -> RenderContext:
        today = timezone.localdate()
        days_overdue = 0
        if debt.due_date:
            days_overdue = max(0, (today - debt.due_date).days)

        return RenderContext(
            name=debt.debtor_name,
            condo_name=self._normalized_condo_trade_name(debt),
            unit=debt.unit,
            amount=debt.amount,
            due_date=debt.due_date,
            days_overdue=days_overdue,
        )

    def _normalized_condo_trade_name(self, debt: Debt) -> Optional[str]:
        """Return the condo trade_name cleaned for display.

        Rules:
        - Read from properties_condo via debt.condo.trade_name
        - Remove occurrences of the words "condominio/condomínio" and "edificio/edifício" (any case)
        - Collapse extra spaces
        - Apply title case
        """
        condo = getattr(debt, 'condo', None)
        raw = getattr(condo, 'trade_name', None)
        if not raw:
            return None

        name = str(raw)
        # Remove target words (with or without accent), case-insensitive
        name = re.sub(r"\b(condominio|condomínio|edificio|edifício|horizontal|residencial)\b", "", name, flags=re.IGNORECASE)
        # Collapse multiple spaces and trim
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            return None
        return name.title()

    def _render_template_text(self, debt: Debt, template: MessageTemplate) -> str:
        ctx = self._build_context(debt)
        # Support common placeholders with safe defaults
        variables: Dict[str, Any] = {
            'name': ctx.name,
            'debtor_name': ctx.name,
            # Backward-compat alias used by some templates
            'condo': ctx.condo_name or '',
            'condo_name': ctx.condo_name or '',
            'unit': ctx.unit or '',
            'amount': str(ctx.amount),
            'due_date': ctx.due_date.strftime('%Y-%m-%d') if ctx.due_date else '',
            'days_overdue': ctx.days_overdue,
        }
        try:
            return template.message_text.format(**variables)
        except Exception:
            # Fallback: best-effort replace known placeholders
            text = template.message_text
            for k, v in variables.items():
                text = text.replace('{' + k + '}', str(v))
            return text

    def _render_fallback_text(self, debt: Debt, *, type_: str) -> str:
        """
        Provide a safe default message when no DB template is configured.
        Kept short to fit typical SMS limits.
        """
        ctx = self._build_context(debt)
        if type_ == 'overdue':
            base = (
                "Olá {name}, aqui é do condomínio {condo_name}. "
                "Consta débito de R$ {amount} do apto {unit}, vencido em {due_date} ({days_overdue}d). "
                "Responda este número para combinarmos a regularização."
            )
        else:
            base = (
                "Olá {name}, lembramos do débito de R$ {amount} do apto {unit} no condomínio {condo_name}. "
                "Podemos te ajudar a regularizar? Responda este número."
            )

        variables: Dict[str, Any] = {
            'name': ctx.name,
            # Backward-compat alias used by some templates
            'condo': ctx.condo_name or '',
            'condo_name': ctx.condo_name or '',
            'unit': ctx.unit or '',
            'amount': str(ctx.amount),
            'due_date': ctx.due_date.strftime('%Y-%m-%d') if ctx.due_date else '',
            'days_overdue': ctx.days_overdue,
        }
        try:
            return base.format(**variables)
        except Exception:
            # As a last resort, interpolate manually
            text = base
            for k, v in variables.items():
                text = text.replace('{' + k + '}', str(v))
            return text

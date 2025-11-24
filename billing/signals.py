import logging
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

from apps.billing.models import Debt
from services.business.debt_notifications_service import DebtNotificationService


@receiver(pre_save, sender=Debt)
def send_overdue_on_activation(sender, instance: Debt, **kwargs):
    """
    When a Debt is activated (status changes to 'active'),
    check if it's overdue and, if so, send class 0 overdue SMS if not already sent.
    """
    try:
        # Only on updates (existing debts)
        old_status = None
        if instance.pk:
            try:
                old = Debt.objects.get(pk=instance.pk)
                old_status = old.status
            except Debt.DoesNotExist:
                old_status = None

        # Detect transition to active
        if instance.status == Debt.STATUS_ACTIVE and old_status != Debt.STATUS_ACTIVE:
            # Overdue check
            today = timezone.localdate()
            if instance.due_date and instance.due_date < today:
                service = DebtNotificationService()
                service.send_overdue_sms(instance, urgency_level=0)
    except Exception as e:
        # Fail safe: do not block save operation due to notification errors
        logging.getLogger(__name__).exception(
            "Debt signal send_overdue_on_activation failed for debt %s: %s",
            getattr(instance, 'id', 'N/A'), e
        )

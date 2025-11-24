from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.conf import settings
from django.core import signing
from django.contrib import messages
from decimal import Decimal
from datetime import datetime
import logging

from .models import Condo, UserCondoAssociation
from apps.billing.models import Debt, InteractionLog
from django.utils import timezone
from services.business.debt_notifications_service import DebtNotificationService

# Create your views here.

@login_required
def properties_list(request):
    """
    View to display the properties page.
    Only accessible to authenticated users.
    """
    logger = logging.getLogger(__name__)

    # Gather diagnostic info about the current user's condo links
    user = request.user
    links_all = UserCondoAssociation.objects.filter(user=user)
    links_active = links_all.filter(has_access__iexact='active')
    links_active_syndic = links_active.filter(role__iexact='syndic')
    condo_ids_qs = links_active_syndic.values_list('condo_id', flat=True)

    # Fetch condos the current user (syndic) has access to via the through model
    condos_qs = (
        Condo.objects.filter(id__in=condo_ids_qs)
        .order_by('trade_name')
        .distinct()
    )

    try:
        # Emit diagnostics only in DEBUG to avoid noisy logs in production
        if getattr(settings, 'DEBUG', False):
            logger.debug(
                "[properties_list] user=%s all_links=%s active_links=%s active_syndic_links=%s condos_count=%s condo_ids=%s",
                getattr(user, 'id', None),
                links_all.count(),
                links_active.count(),
                links_active_syndic.count(),
                condos_qs.count(),
                list(condo_ids_qs),
            )
    except Exception:
        # Logging must never break the view
        pass

    # Pagination
    page_number = request.GET.get('page', 1)
    per_page = 9  # 3 cards per row x 3 rows fits the current design grid nicely
    paginator = Paginator(condos_qs, per_page)
    page_obj = paginator.get_page(page_number)

    # Attach opaque signed tokens to each condo for use in URLs (avoid exposing raw UUIDs)
    try:
        for c in page_obj:
            c.token = signing.dumps(str(c.id), salt='properties.condo')
    except Exception:
        pass

    context = {
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': page_obj.has_other_pages(),
        'condos_page': page_obj,  # alias for clarity in templates
    }
    return render(request, 'metronic/properties/properties.html', context)


@login_required
def property_detail(request, token):
    """Detail page for a single condo restricted to authorized users.

    Authorization: user must have an active 'syndic' association to the condo.
    """
    # Unsign token to get condo UUID (as string)
    try:
        condo_id = signing.loads(token, salt='properties.condo')
    except Exception:
        from django.http import Http404
        raise Http404("Condominium not found")

    condo = get_object_or_404(Condo, id=condo_id)

    has_access = UserCondoAssociation.objects.filter(
        user=request.user,
        condo_id=condo.id,
        has_access__iexact='active',
        role__iexact='syndic',
    ).exists()

    if not has_access:
        # Hide existence details by returning 404 if user isn't allowed
        from django.http import Http404
        raise Http404("Condominium not found")

    # Debts linked to this condo (newest first)
    debts_qs = Debt.objects.filter(condo=condo).order_by('-created_at')

    # Compute real-time debt status counts for the summary card
    today = timezone.localdate()
    debt_counts = {
        'active': debts_qs.filter(status=Debt.STATUS_ACTIVE).count(),
        'pending': debts_qs.filter(status=Debt.STATUS_PENDING).count(),
        # Overdue means due_date older than today among listed debts (any status)
        'overdue': debts_qs.filter(due_date__lt=today).count(),
        # Placeholders (no explicit fields yet)
        'completed': 0,
        'judicial': 0,
        'total': debts_qs.count(),
    }

    # Interactions (for now only SMS) for this condo
    interactions_sms = InteractionLog.objects.filter(
        condo=condo,
        action_type='sms',
    ).order_by('-timestamp')

    # Month selection for the chart (YYYY-MM). Default current month.
    import calendar
    from datetime import date

    month_param = (request.GET.get('month') or '').strip()
    try:
        year, month = map(int, month_param.split('-'))
        selected_month = date(year, month, 1)
    except Exception:
        selected_month = date(today.year, today.month, 1)

    last_day = calendar.monthrange(selected_month.year, selected_month.month)[1]
    month_start = selected_month
    month_end = date(selected_month.year, selected_month.month, last_day)

    # Filter interactions within selected month window (convert timestamp to date)
    interactions_month = interactions_sms.filter(
        timestamp__date__gte=month_start,
        timestamp__date__lte=month_end,
    )

    # Build per-day counts
    labels = [str(d) for d in range(1, last_day + 1)]
    data_counts = [0] * last_day
    for log in interactions_month:
        try:
            ts = timezone.localtime(log.timestamp)
        except Exception:
            ts = log.timestamp
        day_idx = getattr(ts, 'day', None) or getattr(getattr(ts, 'date', lambda: None)(), 'day', 1)
        if isinstance(day_idx, int) and 1 <= day_idx <= last_day:
            data_counts[day_idx - 1] += 1

    # Build month options (last 6 months including current)
    def month_iter(back: int = 6):
        m = today.month
        y = today.year
        for _ in range(back):
            yield y, m
            m -= 1
            if m == 0:
                m = 12
                y -= 1

    month_options = []
    for y, m in month_iter(6):
        val = f"{y:04d}-{m:02d}"
        label = f"{m:02d}/{y}"
        month_options.append({'value': val, 'label': label})

    context = {
        'condo': condo,
        'debts': debts_qs,
        'token': token,
        'debt_counts': debt_counts,
        'interactions_sms': interactions_sms,
        'chart': {
            'labels': labels,
            'data': data_counts,
            'selected_month': f"{selected_month.year:04d}-{selected_month.month:02d}",
        },
        'month_options': month_options,
    }
    return render(request, 'metronic/properties/property.html', context)


@login_required
def debt_create(request, token):
    """Create a new Debt for a condo identified by signed token.

    Accepts POSTs from the debt modal form in property.html and persists to DB.
    """
    # Resolve condo from token
    try:
        condo_id = signing.loads(token, salt='properties.condo')
    except Exception:
        from django.http import Http404
        raise Http404("Condominium not found")

    condo = get_object_or_404(Condo, id=condo_id)

    # Authorization: same as property_detail
    has_access = UserCondoAssociation.objects.filter(
        user=request.user,
        condo_id=condo.id,
        has_access__iexact='active',
        role__iexact='syndic',
    ).exists()

    if not has_access:
        from django.http import Http404
        raise Http404("Condominium not found")

    if request.method != 'POST':
        return redirect('properties:property_detail', token=token)

    # Extract and validate fields from form
    debtor_name = request.POST.get('target_title', '').strip()
    cpf = request.POST.get('cpf', '').strip()
    phone = request.POST.get('phone', '').strip()
    unit = request.POST.get('unidade', '').strip()
    details = request.POST.get('target_details', '').strip() or None
    channels = request.POST.getlist('communication[]')
    request_verification = request.POST.get('request_verification', '1') in ('1', 'on', 'true', 'True')

    # due_date and amount parsing
    due_date_str = request.POST.get('due_date')
    amount_str = request.POST.get('valor', '0').replace(',', '.')

    errors = []
    if not debtor_name:
        errors.append('Nome do devedor é obrigatório.')
    if not cpf:
        errors.append('CPF é obrigatório.')
    if not unit:
        errors.append('Unidade é obrigatória.')
    try:
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
    except Exception:
        errors.append('Data de vencimento inválida.')
        due_date = None
    try:
        amount = Decimal(amount_str)
    except Exception:
        errors.append('Valor inválido.')
        amount = Decimal('0')

    if errors:
        for e in errors:
            messages.error(request, e)
        return redirect('properties:property_detail', token=token)

    # Create debt
    Debt.objects.create(
        condo=condo,
        debtor_name=debtor_name,
        cpf=cpf,
        phone=phone or None,
        unit=unit,
        due_date=due_date,
        amount=amount,
        details=details,
        channels=channels,
        request_verification=request_verification,
    )

    messages.success(request, 'Cobrança criada com sucesso.')
    return redirect('properties:property_detail', token=token)


@login_required
def debt_toggle_status(request, token, debt_id):
    """Toggle a Debt status between pending and active.

    POST-only. Scoped by condo token and requires syndic access.
    """
    if request.method != 'POST':
        return redirect('properties:property_detail', token=token)

    # Resolve condo from token
    try:
        condo_id = signing.loads(token, salt='properties.condo')
    except Exception:
        from django.http import Http404
        raise Http404("Condominium not found")

    condo = get_object_or_404(Condo, id=condo_id)

    # Authorization
    has_access = UserCondoAssociation.objects.filter(
        user=request.user,
        condo_id=condo.id,
        has_access__iexact='active',
        role__iexact='syndic',
    ).exists()
    if not has_access:
        from django.http import Http404
        raise Http404("Condominium not found")

    debt = get_object_or_404(Debt, id=debt_id, condo=condo)

    debt.status = Debt.STATUS_ACTIVE if debt.status != Debt.STATUS_ACTIVE else Debt.STATUS_PENDING
    debt.save(update_fields=['status', 'updated_at'])

    # Trigger initial overdue SMS on activation (idempotent in service)
    try:
        if debt.status == Debt.STATUS_ACTIVE:
            today = timezone.localdate()
            if debt.due_date and debt.due_date < today:
                DebtNotificationService().send_overdue_sms(debt, urgency_level=0)
    except Exception as e:
        # Do not block UI flow due to notification errors, but log for troubleshooting
        logging.getLogger(__name__).exception(
            "Debt toggle notification failed for debt %s: %s",
            str(debt.id), e
        )

    # If AJAX/JSON requested, return JSON without redirect to avoid page reload
    wants_json = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
    if wants_json:
        return JsonResponse({
            'ok': True,
            'debt_id': str(debt.id),
            'status': debt.status,
        })

    return redirect('properties:property_detail', token=token)


@login_required
def debt_toggle_channel(request, token, debt_id, channel: str):
    """Toggle a single communication channel in Debt.channels.

    POST-only. Channels: whatsapp|call|sms
    """
    if request.method != 'POST':
        return redirect('properties:property_detail', token=token)

    # Resolve condo from token
    try:
        condo_id = signing.loads(token, salt='properties.condo')
    except Exception:
        from django.http import Http404
        raise Http404("Condominium not found")

    condo = get_object_or_404(Condo, id=condo_id)

    # Authorization
    has_access = UserCondoAssociation.objects.filter(
        user=request.user,
        condo_id=condo.id,
        has_access__iexact='active',
        role__iexact='syndic',
    ).exists()
    if not has_access:
        from django.http import Http404
        raise Http404("Condominium not found")

    allowed = {'whatsapp', 'call', 'sms'}
    channel = (channel or '').lower()
    if channel not in allowed:
        # Silently ignore invalid channel names
        wants_json = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
        if wants_json:
            return JsonResponse({'ok': False, 'error': 'invalid_channel'}, status=400)
        return redirect('properties:property_detail', token=token)

    debt = get_object_or_404(Debt, id=debt_id, condo=condo)

    channels = list(debt.channels or [])
    if channel in channels:
        channels = [c for c in channels if c != channel]
    else:
        channels.append(channel)

    # Deduplicate while preserving simple order whatsapp,call,sms for consistency
    order = ['whatsapp', 'call', 'sms']
    channels_set = set(channels)
    channels_sorted = [c for c in order if c in channels_set]

    debt.channels = channels_sorted
    debt.save(update_fields=['channels', 'updated_at'])

    wants_json = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
    if wants_json:
        return JsonResponse({
            'ok': True,
            'debt_id': str(debt.id),
            'channel': channel,
            'enabled': channel in channels_sorted,
            'channels': channels_sorted,
        })

    return redirect('properties:property_detail', token=token)

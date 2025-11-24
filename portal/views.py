from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.dateparse import parse_date
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.conf import settings
import logging
import json

from services.utils.validators import normalize_digits, validate_cnpj
from services.external.receitaws.receita_ws import fetch_by_cnpj
from apps.properties.models import Condo, UserCondoAssociation

from services.external.viacep.viacep import ViaCEPService, ViaCEPError

# Module logger
logger = logging.getLogger(__name__)

# Create your views here.
@ensure_csrf_cookie
@login_required
def dashboard_view(request):
    """
    View function for the dashboard page of the portal.
    Only accessible to logged-in users.
    """
    # The login_required decorator ensures only authenticated users can access this view
    # The user information is automatically available in the template via request.user
    return render(request, 'metronic/portal/dashboard.html')


@login_required
@require_GET
def cep_lookup(request):
    """Lookup address information by CEP using ViaCEPService with DB caching.

    Query Params:
    - cep: Brazilian postal code (formats accepted: 12345678 or 12345-678)

    Returns JSON:
    {
        "success": true,
        "data": {
            "street": str,
            "district": str,
            "city": str,
            "state": str,
            "postal_code": str,
            "complement": str,
            "ibge_code": str,
            "gia_code": str,
            "ddd": str,
            "siafi_code": str
        }
    }
    or on error:
    {
        "success": false,
        "error": str,
        "code": str
    }
    """
    cep = (request.GET.get('cep') or "").strip()

    service = ViaCEPService()

    # Validate format early to avoid unnecessary service calls
    if not service.is_valid_cep_format(cep):
        return JsonResponse({
            "success": False,
            "error": "Formato de CEP inválido. Use 99999-999 ou 8 dígitos.",
            "code": "invalid_format"
        }, status=400)

    try:
        address = service.get_address_by_cep(cep)
        return JsonResponse({
            "success": True,
            "data": address
        })
    except ViaCEPError as e:
        # Extract a structured error if available
        error_payload = getattr(e, 'to_dict', lambda: {"message": str(e), "error_code": "unknown"})()
        return JsonResponse({
            "success": False,
            "error": error_payload.get("message", str(e)),
            "code": error_payload.get("error_code", "unknown")
        }, status=422)
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": "Erro interno ao buscar CEP.",
            "code": "internal_error"
        }, status=500)


@login_required
@require_GET
def cnpj_lookup(request: HttpRequest):
    """Lookup company information by CNPJ using ReceitaWS client.

    Query Params:
    - cnpj: Brazilian CNPJ (formats accepted: 00.000.000/0000-00 or 14 digits)

    Returns JSON:
    {
        "success": true,
        "data": {
            "legal_name": str,
            "trade_name": str,
            "situation": str,
            "postal_code": str,
            "street": str,
            "number": str,
            "complement": str,
            "district": str,
            "city": str,
            "state": str,
            "country": "BR"
        }
    }
    """
    raw = (request.GET.get('cnpj') or "").strip()
    digits = normalize_digits(raw)
    # Basic format check
    if len(digits) != 14:
        return JsonResponse({
            "success": False,
            "error": "Formato de CNPJ inválido. Informe 14 dígitos.",
            "code": "invalid_format",
        }, status=400)
    # Checksum validation
    try:
        validate_cnpj(digits)
    except Exception:
        return JsonResponse({
            "success": False,
            "error": "CNPJ inválido.",
            "code": "invalid_cnpj",
        }, status=422)

    try:
        data = fetch_by_cnpj(digits)
        return JsonResponse({
            "success": True,
            "data": {
                "legal_name": data.legal_name,
                "trade_name": data.trade_name,
                "situation": data.situation,
                "postal_code": data.postal_code,
                "street": data.street,
                "number": data.number,
                "complement": data.complement,
                "district": data.district,
                "city": data.city,
                "state": data.state,
                "country": data.country,
            }
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": "Erro ao consultar dados do CNPJ na ReceitaWS.",
            "code": "receitaws_error",
        }, status=502)


@login_required
@require_POST
@transaction.atomic
def create_property(request: HttpRequest):
    """Create a Condo from Síndico/Administrador flow.

    Accepts JSON or form-urlencoded body. Expected fields (subset):
    - account_type: must be 'manager'
    - condominium_cnpj (required)
    - cep, numero (required)
    - rua, bairro, cidade, estado, pais (optional)
    - legal_name, trade_name (optional; will be fetched via CNPJ if possible)
    - quantidade_blocos, quantidade_unidades (optional)
    - gestao_inicio, gestao_fim (dd/mm/yyyy or ISO)
    """
    # Parse payload supporting JSON and form
    if request.content_type and 'application/json' in request.content_type:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            payload = {}
    else:
        payload = request.POST.dict()

    account_type = (payload.get('account_type') or '').strip()
    if account_type != 'manager':
        return JsonResponse({
            "success": False,
            "error": "Fluxo inválido. Este endpoint é exclusivo para Síndico/Administrador.",
            "code": "invalid_flow"
        }, status=400)

    raw_cnpj = (payload.get('condominium_cnpj') or '').strip()
    digits = normalize_digits(raw_cnpj)
    logger.debug("[create_property] payload parsed: account_type=%s raw_cnpj=%s digits=%s user=%s", account_type, raw_cnpj, digits, getattr(request.user, 'id', None))
    if len(digits) != 14:
        return JsonResponse({
            "success": False,
            "error": "CNPJ inválido.",
            "code": "invalid_cnpj"
        }, status=422)
    try:
        validate_cnpj(digits)
    except Exception:
        return JsonResponse({
            "success": False,
            "error": "CNPJ inválido.",
            "code": "invalid_cnpj"
        }, status=422)

    # Duplicate guard: avoid IntegrityError later and return a clear message
    if Condo.objects.filter(tax_id=digits).exists():
        return JsonResponse({
            "success": False,
            "error": "Já existe um condomínio cadastrado com este CNPJ.",
            "code": "duplicate_cnpj",
        }, status=409)

    # Address inputs are optional in the first onboarding step; allow creation without enforcing them here.
    # We still capture them if provided and also try to backfill from ReceitaWS when available.
    cep = (payload.get('cep') or '').strip()
    numero = (payload.get('numero') or '').strip()

    # Create and enrich Condo
    condo = Condo(tax_id=digits)
    # Try to enrich with ReceitaWS; fallback to provided names
    legal_name = (payload.get('legal_name') or '').strip() or None
    trade_name = (payload.get('trade_name') or '').strip() or None
    try:
        data = fetch_by_cnpj(digits)
        # Inline mapping to avoid importing map to keep dependency surface minimal here
        condo.receitaws_status = data.status
        condo.receitaws_last_sync_at = None  # set by model save/update elsewhere if needed
        condo.receitaws_raw = data.raw
        condo.opening_date = data.opening_date
        # legal_nature_code vindo da Receita pode ser uma descrição longa.
        # Normalizamos para um código curto (até 10 chars) para atender ao modelo.
        ln = (data.legal_nature_code or '')
        if ln:
            # tentar extrair um código no início (ex.: "213-5 - Empresário" -> "213-5")
            import re
            m = re.match(r"^([0-9\-\.\/]+)", ln.strip())
            ln_code = (m.group(1) if m else ln.strip())[:10]
            condo.legal_nature_code = ln_code
        condo.company_size = data.company_size
        condo.situation = data.situation
        condo.situation_date = data.situation_date
        condo.primary_cnae_code = data.primary_cnae_code
        condo.secondary_cnaes = data.secondary_cnaes
        condo.partners_count = data.partners_count
        if data.capital_social is not None:
            condo.capital_social = data.capital_social
        if data.legal_name:
            legal_name = data.legal_name
        if data.trade_name:
            trade_name = data.trade_name
        # Address defaults
        if not payload.get('rua') and data.street:
            payload['rua'] = data.street
        if not payload.get('bairro') and data.district:
            payload['bairro'] = data.district
        if not payload.get('cidade') and data.city:
            payload['cidade'] = data.city
        if not payload.get('estado') and data.state:
            payload['estado'] = data.state
        if not payload.get('pais') and data.country:
            payload['pais'] = data.country
        # If CEP/numero missing, use Receita values when present
        if not cep and data.postal_code:
            cep = data.postal_code
        if not numero and data.number:
            numero = str(data.number)
    except Exception:
        # Continue with provided data only
        pass

    # Identity fallback: if only one name is present, reuse it for the other
    if legal_name and not trade_name:
        trade_name = legal_name
    elif trade_name and not legal_name:
        legal_name = trade_name

    if not legal_name or not trade_name:
        # Como fallback, usar um nome padrão baseado no CNPJ para não bloquear o cadastro
        placeholder = f"Condomínio {digits}"
        legal_name = legal_name or placeholder
        trade_name = trade_name or placeholder

    # Assign identity and address
    condo.legal_name = legal_name
    condo.trade_name = trade_name
    # CEP: normalizar para apenas dígitos para não estourar max_length
    condo.postal_code = normalize_digits(cep)
    condo.street = (payload.get('rua') or None)
    condo.number = (numero or None)
    condo.complement = (payload.get('complemento') or None)
    condo.district = (payload.get('bairro') or None)
    condo.city = (payload.get('cidade') or None)
    condo.state = (payload.get('estado') or None)
    condo.country = (payload.get('pais') or 'BR')

    # Structure
    try:
        condo.num_blocks = int(payload.get('quantidade_blocos') or 0) or None
    except Exception:
        condo.num_blocks = None
    try:
        condo.num_units = int(payload.get('quantidade_unidades') or 0) or None
    except Exception:
        condo.num_units = None

    # Term dates: accept dd/mm/yyyy or ISO
    def parse_br_date(s: str):
        s = (s or '').strip()
        if not s:
            return None
        # try dd/mm/yyyy
        try:
            dd, mm, yyyy = s.split('/')
            return parse_date(f"{yyyy}-{mm}-{dd}")
        except Exception:
            return parse_date(s)

    condo.term_start = parse_br_date(payload.get('gestao_inicio') or '')
    condo.term_end = parse_br_date(payload.get('gestao_fim') or '')

    try:
        condo.save()
        # Avoid logging sensitive tax_id in production logs
        logger.info("[create_property] Condo saved id=%s user=%s", condo.id, getattr(request.user, 'id', None))

        # Link creator as pending syndic in properties_usercondo
        # TODO: Build a syndic approval tool (admin panel or API endpoint)
        #       to review and activate pending syndics (has_access='pending' → 'active')
        #       Should include email notification, audit log, and rejection option.
        assoc = None
        assoc_created = None
        assoc_mode = None
        try:
            assoc, created = UserCondoAssociation.objects.get_or_create(
                user=request.user,
                condo=condo,
                role='syndic',
                defaults={
                    'has_access': 'pending',
                    'start_date': condo.term_start,
                    'end_date': condo.term_end,
                    'permissions': {},
                }
            )
            assoc_created = created
            assoc_mode = 'char'
            logger.info(
                "[create_property] UserCondoAssociation %s: assoc_id=%s user=%s condo=%s role=%s has_access=%s",
                'created' if created else 'exists', getattr(assoc, 'id', None), getattr(request.user, 'id', None), condo.id, 'syndic', getattr(assoc, 'has_access', None)
            )
        except Exception as assoc_err:
            # Do not fail the condo creation if association creation fails; log for investigation
            logger.exception("[create_property] Failed to create UserCondoAssociation for user=%s condo=%s: %s", getattr(request.user, 'id', None), condo.id, assoc_err)

        resp = {
            "success": True,
            "id": str(condo.id)
        }
        # Lightweight debug payload to help validate end-to-end during development
        if getattr(settings, 'DEBUG', False):
            try:
                resp["debug"] = {
                    "user_id": str(getattr(request.user, 'id', '')),
                    "assoc_created": bool(assoc_created) if assoc_created is not None else None,
                    "assoc_id": str(getattr(assoc, 'id', '')) if assoc else None,
                    "assoc_mode": assoc_mode,
                }
            except Exception:
                pass

        return JsonResponse(resp, status=201)
    except ValidationError as ve:
        # Validation errors from model.clean/full_clean
        details = getattr(ve, 'message_dict', None) or getattr(ve, 'messages', None)
        return JsonResponse({
            "success": False,
            "error": "Dados inválidos no cadastro do condomínio.",
            "code": "validation_error",
            "details": details,
        }, status=422)
    except IntegrityError:
        # Likely UNIQUE index on CNPJ (digits-only)
        return JsonResponse({
            "success": False,
            "error": "Já existe um condomínio cadastrado com este CNPJ.",
            "code": "duplicate_cnpj",
        }, status=409)
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": "Erro ao criar condomínio.",
            "code": "save_error"
        }, status=422)

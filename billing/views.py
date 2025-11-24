from io import BytesIO
from datetime import date, timedelta

from django.conf import settings  # Para placeholders configuráveis em settings.py
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404

from apps.properties.models import Condo, UserCondoAssociation
from .models import Debt

from jinja2 import Template
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import datetime
from decimal import Decimal

from apps.billing.templates.contract_template_a_vista import contract_template

def _format_money_brl(value) -> str:
    """
    Formata o dinheiro do jeito brasileiro
     Por exemplo, 1234.56 vira "1.234,56".

    :param value: Entrada do numero a ser formatado.
    :return: Saida do valor numerico em string.
    """
    try:
        v = float(value or 0)
    except Exception:
        v = 0.0
    # 1.234,56
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@login_required
def generate_contract_pdf(request, debtor_id: str):
    """Gera contrato de confissão/renegociação de dívida com segurança e dados reais.
    Segurança/Autorização:
    - Se houver token assinado (?token=...), resolve o condomínio via token (salt 'properties.condo')
      e valida que o usuário logado é síndico ativo do condomínio.
    - Sem token, valida que o usuário é síndico ativo do condomínio pertenecente à dívida.
    Automação:
    - Preenche template com dados do Debt (cpf, unit, amount, due_date) e Condo.
    - Usa fallbacks seguros quando o dado não existir.
    """
    token = request.GET.get('token')
    condo = None
    debt = None

    if token:
        # 1) Resolver condo a partir do signed token
        try:
            condo_id = signing.loads(token, salt='properties.condo')
        except signing.BadSignature:
            raise Http404("Token inválido ou expirado")
        except Exception:
            raise Http404("Condomínio não encontrado")

        condo = get_object_or_404(Condo, id=condo_id)

        # 2) Checar auth (síndico ativo)
        has_access = UserCondoAssociation.objects.filter(
            user=request.user,
            condo=condo,
            has_access__iexact='active',
            role__iexact='syndic',
        ).exists()
        if not has_access:
            raise Http404("Acesso negado ao condomínio")

        # 3) Buscar a dívida vinculada ao condomínio
        debt = get_object_or_404(Debt, id=debtor_id, condo=condo)
    else:
        # Sem token: buscar a dívida e validar acesso pelo condomínio dela
        debt = get_object_or_404(Debt, id=debtor_id)
        condo = debt.condo
        has_access = UserCondoAssociation.objects.filter(
            user=request.user,
            condo=condo,
            has_access__iexact='active',
            role__iexact='syndic',
        ).exists()
        if not has_access:
            raise Http404("Acesso negado ao condomínio")

    # 4) Montar dados do contrato
    due = debt.due_date or (date.today() + timedelta(days=30))
    debt_amount_numeric = float(debt.amount or 0)

    # Formatação de data PT-BR (sem helper global)
    meses_pt = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    def format_date_pt_br(d: date) -> str:
        return f"{d.day:02d} de {meses_pt[d.month - 1]} de {d.year}"

    # Valor por extenso com num2words (sem helper global)
    try:
        from num2words import num2words  # type: ignore
        v = float(debt_amount_numeric or 0)
        reais = int(v)
        centavos = int(round((v - reais) * 100))
        parte_reais = f"{num2words(reais, lang='pt_BR')} {'real' if reais == 1 else 'reais'}" if reais else "zero reais"
        parte_centavos = (
            f" e {num2words(centavos, lang='pt_BR')} {'centavo' if centavos == 1 else 'centavos'}"
            if centavos else ""
        )
        debt_amount_words = (parte_reais + parte_centavos).replace(" e zero centavos", "")
    except Exception:
        # Se num2words não estiver disponível, deixa em branco para não quebrar
        debt_amount_words = ""

    endereco_condo_partes = [
        condo.street,
        condo.number,
        condo.complement,
        condo.district,
        condo.city,
        condo.state,
        condo.postal_code,
    ]
    endereco_condo = ', '.join([str(p) for p in endereco_condo_partes if p]).strip(', ')

    # Dados de síndico (fallbacks seguros)
    syndic = getattr(condo, 'current_syndic', None)
    syndic_name = request.user.get_full_name() if request.user else getattr(syndic, 'get_full_name', lambda: str(
        syndic) if syndic else "").__call__() if syndic else ""
    if not syndic_name and syndic:
        syndic_name = getattr(syndic, 'username', '')

    # Deriva período como MM/YYYY da dívida (única competência)
    debt_period = due.strftime("%m/%Y")

    data = {
        # Devedor
        'debtor_name': debt.debtor_name,
        'debtor_nationality': 'brasileira',  # opcional/fallback
        'debtor_cpf': debt.cpf,
        'debtor_rg': '',  # não disponível
        'debtor_birthdate': '',  # não disponível
        'debtor_address': f"Unidade {debt.unit} situado na {endereco_condo}" if endereco_condo else f"Unidade {debt.unit}",
        'debtor_neighborhood': condo.district or '',
        'debtor_cep': condo.postal_code or '',
        'debtor_city': condo.city or '',
        'debtor_state': condo.state or '',
        'debtor_email': '',  # não disponível
        'debtor_whatsapp': debt.phone or '',

        # Credor (Condomínio)
        'credor_name': (condo.trade_name or condo.legal_name or '').upper(),
        'credor_cnpj': condo.tax_id or '',
        'credor_address': ', '.join([p for p in [condo.street or '', str(condo.number or '')] if p]).strip(', '),
        'credor_neighborhood': condo.district or '',
        'credor_cep': condo.postal_code or '',
        'credor_city': condo.city or '',
        'credor_state': condo.state or '',
        'credor_email': '',  # não disponível no model

        # Síndico
        'sindico_election_date': format_date_pt_br(condo.term_start) if getattr(condo, 'term_start', None) else '',
        'sindico_name': syndic_name,
        'sindico_profession': '',  # não disponível
        'sindico_cpf': '',  # não disponível
        'sindico_address': endereco_condo,
        'sindico_neighborhood': condo.district or '',
        'sindico_cep': condo.postal_code or '',
        'sindico_city': condo.city or '',
        'sindico_state': condo.state or '',

        # Valores
        'debt_amount': _format_money_brl(debt_amount_numeric),
        'debt_amount_words': debt_amount_words,
        'debt_periods': debt.details or debt_period,
        'total_debt': _format_money_brl(debt_amount_numeric),  # igual por ora
        'total_debt_words': debt_amount_words,
        'due_date': due.strftime('%d/%m/%Y'),

        # Disposições e localização
        'assembly_date': '',  # não disponível; pode ser preenchido manualmente
        'forum_city': condo.city or '',
        'forum_state': condo.state or '',
        'city': condo.city or '',
        'current_date': format_date_pt_br(datetime.date.today()),

        # Testemunha (fallback: usuário logado)
        'witness_name': getattr(request.user, 'get_full_name', lambda: str(request.user))(),
        'witness_cpf': '',
        'witness_email': getattr(request.user, 'email', '') or '',
    }

    # 5) Render template
    template = Template(contract_template)
    rendered_text = template.render(data)

    # 6) Gerar PDF profissional com Platypus (wrapping automático, estilos)
    buffer = BytesIO()
    # Usar A4 com margens ~2cm para documentos brasileiros
    cm = 0.393701 * inch
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ContractTitle', fontSize=14, leading=18, alignment=TA_CENTER, spaceAfter=12,
                              fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='Clause', fontSize=12, leading=16, alignment=TA_LEFT, spaceBefore=12, spaceAfter=6,
                              fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='Paragraph', fontSize=11, leading=14, alignment=TA_JUSTIFY, spaceAfter=8,
                              fontName='Helvetica'))
    styles.add(ParagraphStyle(name='Signature', fontSize=12, leading=16, alignment=TA_LEFT, spaceBefore=24))

    Story = []

    # Split rendered_text por linhas vazias para seções/parágrafos
    sections = [s for s in rendered_text.split('\n\n') if s.strip()]
    for section in sections:
        section = section.strip().replace('\n', ' ')  # Junta linhas dentro de parágrafo para justify
        if section.startswith('CONTRATO DE'):
            Story.append(Paragraph(section, styles['ContractTitle']))
            Story.append(Spacer(1, 0.25 * inch))
        elif section.startswith('CLÁUSULA') or section.startswith('PARÁGRAFO') or section.startswith(
                'DO ') or section.startswith('DISPOSIÇÕES'):
            Story.append(Paragraph(section, styles['Clause']))
        else:
            Story.append(Paragraph(section, styles['Paragraph']))

    # Observação: Assinaturas e testemunhas já constam no template. Se desejar forçar em nova página:
    # Story.append(PageBreak())

    doc.build(Story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    filename = f"contrato_{debt.debtor_name.replace(' ', '_')}_{debt.unit}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@login_required
def debt_boleto_pdf(request, token: str, debt_id: str):
    """Gera um boleto (PDF) para uma dívida específica no ambiente de testes.

    Segurança/Autorização:
    - O usuário precisa ter acesso ativo como síndico ao condomínio vinculado ao débito.
    - O condomínio é resolvido via token assinado (mesma estratégia da página de detalhes).

    Melhorias:
    - Adicionados campos faltantes: instrucoes, demonstrativo, local_pagamento, sacado como lista com endereço.
    - Placeholders bancários vindos de settings.py (ex: adicione ao settings: BOLETO_AGENCIA='0001', etc.).
    - Handling de erros mais robusto.
    - Nosso número formatado para Bradesco (zfill para 11 dígitos, mas ajuste conforme carteira).
    - Valor inclui float conversion segura.
    """
    # 1) Resolver condomínio a partir do token assinado
    try:
        condo_id = signing.loads(token, salt='properties.condo')
    except signing.BadSignature:
        raise Http404("Token inválido ou expirado")
    except Exception:
        raise Http404("Condomínio não encontrado")

    condo = get_object_or_404(Condo, id=condo_id)

    # 2) Checar autorização (síndico ativo)
    has_access = UserCondoAssociation.objects.filter(
        user=request.user,
        condo=condo,
        has_access__iexact='active',
        role__iexact='syndic',
    ).exists()
    if not has_access:
        raise Http404("Acesso negado ao condomínio")

    # 3) Buscar a dívida vinculada ao condomínio
    debt = get_object_or_404(Debt, id=debt_id, condo=condo)

    # 4) Montar o boleto usando python3-boleto + reportlab
    #    Usaremos Bradesco; para outros bancos, troque BoletoBradesco por ex: BoletoItau
    try:
        from pyboleto.bank.bradesco import BoletoBradesco
        from pyboleto.pdf import BoletoPDF
    except ImportError as e:
        # Logar erro em produção (use logging), mas por ora, response amigável
        return HttpResponse(f"Biblioteca de boletos não disponível: {str(e)}", status=500)

    boleto = BoletoBradesco()

    # Cedente (condomínio)
    boleto.cedente = condo.trade_name.title() or condo.legal_name.title()
    boleto.cedente_documento = condo.tax_id

    # Endereço do cedente (filtrado e juntado)
    endereco_partes = [
        condo.street,
        condo.number,
        condo.complement,
        condo.district,
        condo.city,
        condo.state,
        condo.postal_code,
    ]
    boleto.cedente_endereco = ', '.join([str(p) for p in endereco_partes if p]).strip(', ').title() or 'Endereço não informado'

    # Configuração bancária (use settings para não hardcode; ex: em settings.py defina BOLETO_AGENCIA etc.)
    boleto.agencia_cedente = getattr(settings, 'BOLETO_AGENCIA', '0001')
    boleto.conta_cedente = getattr(settings, 'BOLETO_CONTA', '000001')
    boleto.carteira = getattr(settings, 'BOLETO_CARTEIRA', '06')  # Para Bradesco, comum '06' ou '09'

    # Dados do título
    boleto.nosso_numero = str(debt.id.int % 99999999999).zfill(11)  # Zfill para 11 dígitos (padrão Bradesco)
    boleto.numero_documento = boleto.nosso_numero
    boleto.data_documento = date.today()
    boleto.data_processamento = date.today()
    boleto.data_vencimento = debt.due_date or (date.today() + timedelta(days=30))  # Default se null
    boleto.valor_documento = float(debt.amount or 0.0)  # Garanta float


    boleto.local_pagamento = "Pagável em qualquer banco até o vencimento ou via app bancário."
    boleto.instrucoes = [
        "Após o vencimento, cobrar multa de 2% + juros de 1% ao mês.",
        "Não receber após 30 dias de vencido sem contato prévio.",
        "Em caso de dúvida, contate o síndico",
        "Pagamento refere-se a dívida de condomínio: {}".format(condo.trade_name.title()),
    ]
    boleto.demonstrativo = [
        "Dívida de Condomínio:",
        "Unidade: {}".format(debt.unit),
        "Valor original: R$ {:.2f}".format(float(debt.amount or 0.0)),
        "Total a pagar: R$ {:.2f}".format(float(debt.amount or 0.0)),  # Adicione lógica de juros se precisar
    ]

    # Sacado (devedor) como lista para múltiplas linhas (inclua endereço se disponível no model Debt)
    boleto.sacado = [
        debt.debtor_name or "Devedor Exemplo",
        f"CPF: {debt.cpf or '000.000.000-00'}",
        # Adicione endereço do devedor se existir no model (ex: debt.debtor_street etc.)
        # Por ora, placeholder; ajuste conforme seu Debt model
        f"Endereço: {condo.street.title()}, {condo.number} Unidade: {debt.unit or 'N/A'}",
    ]

    # 5) Gerar PDF em memória
    buffer = BytesIO()
    try:
        pdf = BoletoPDF(buffer)
        pdf.drawBoleto(boleto)
        pdf.save()
        pdf_bytes = buffer.getvalue()
    except Exception as e:
        return HttpResponse(f"Erro ao gerar PDF: {str(e)}", status=500)
    finally:
        buffer.close()

    # 6) Response (lembrar que inline para visualização; 'attachment' download direto)
    filename = f"boleto_{condo.trade_name.replace(' ', '_')}_{debt.id}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f"inline; filename={filename}"
    return response
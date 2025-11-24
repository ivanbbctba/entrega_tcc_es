from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    path('<str:token>/debts/<uuid:debt_id>/boleto/', views.debt_boleto_pdf, name='debt_boleto_pdf'),
    # Contract PDF generation (token is passed via querystring and validated in the view)
    path('debts/<uuid:debtor_id>/contract/', views.generate_contract_pdf, name='debt_contract_pdf'),
]

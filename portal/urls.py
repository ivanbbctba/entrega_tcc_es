from django.urls import path
from django.contrib.auth.decorators import login_required
from . import views

app_name = "apps.portal"

urlpatterns = [
    path("dashboard/", login_required(views.dashboard_view), name="dashboard"),
    path("api/cep-lookup/", login_required(views.cep_lookup), name="cep_lookup"),
    path("api/cnpj-lookup/", login_required(views.cnpj_lookup), name="cnpj_lookup"),
    path("api/properties/create/", login_required(views.create_property), name="create_property"),
]
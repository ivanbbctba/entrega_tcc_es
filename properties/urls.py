from django.urls import path
from . import views

app_name = 'properties'

urlpatterns = [
    path('', views.properties_list, name='properties_list'),
    # Use an opaque signed token instead of exposing the raw UUID in the URL
    path('<str:token>/', views.property_detail, name='property_detail'),
    path('<str:token>/debts/create/', views.debt_create, name='debt_create'),
    # Toggle endpoints for debts
    path('<str:token>/debts/<uuid:debt_id>/toggle-status/', views.debt_toggle_status, name='debt_toggle_status'),
    path('<str:token>/debts/<uuid:debt_id>/toggle-channel/<str:channel>/', views.debt_toggle_channel, name='debt_toggle_channel'),
]
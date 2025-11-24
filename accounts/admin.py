from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, UserProfile, Phone

class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ('phone_number', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    fieldsets = (
        (None, {'fields': ('phone_number', 'password')}),
        ('Login History', {'fields': ('login_ips',)}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'password1', 'password2', 'role', 'is_staff', 'is_active')}
        ),
    )
    search_fields = ('phone_number',)
    ordering = ('phone_number',)

class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'gov_id', 'gov_id_state', 'cpf_cnpj', 'date_completed', 'created_at')
    search_fields = ('user__phone_number', 'full_name', 'gov_id', 'cpf_cnpj')
    list_filter = ('date_completed', 'created_at')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('user', 'full_name')}),
        ('Identification', {'fields': ('gov_id', 'gov_id_state', 'tax_id', 'cpf_cnpj', 'nationality', 'birthday')}),
        ('Address', {'fields': ('default_address_id',)}),
        ('Communication Preferences', {'fields': ('preferred_communication_email', 'preferred_communication_sms', 'preferred_communication_whatsapp', 'allow_marketing')}),
        ('Metadata', {'fields': ('date_completed', 'who_created', 'creation_ip', 'created_at', 'updated_at')}),
    )

class PhoneAdmin(admin.ModelAdmin):
    list_display = ('user', 'number', 'type', 'is_primary', 'is_verified', 'created_at')
    search_fields = ('user__phone_number', 'number')
    list_filter = ('type', 'is_primary', 'is_verified', 'created_at')
    readonly_fields = ('created_at', 'updated_at')

# Register the models with their custom admins
admin.site.register(User, CustomUserAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(Phone, PhoneAdmin)

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField
import json
import uuid

class Phone(models.Model):
    """
    Phone numbers associated with a user.
    """
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='phones')
    number = models.CharField(max_length=20, verbose_name="Phone Number")
    type = models.CharField(max_length=20, choices=[
        ('MOBILE', 'Mobile'),
        ('HOME', 'Home'),
        ('WORK', 'Work'),
        ('OTHER', 'Other')
    ], default='MOBILE')
    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.number} ({self.get_type_display()})"

    class Meta:
        verbose_name = "Phone"
        verbose_name_plural = "Phones"

class UserManager(BaseUserManager):
    use_in_migrations = True

    # ------- helpers internos -------------

    def _validate_user_data(self, phone_number, password, **extra_fields):
        """
        Valida os dados do usuário antes da criação
        """
        if not phone_number:
            raise ValueError('O telefone é obrigatório')
        if not password:
            raise ValueError('A senha é obrigatória')

        return phone_number, password, extra_fields

    # ------- API pública ------------------
    def create_user(self, phone_number, password=None, **extra_fields):
        """
        Cria e salva um usuário com o telefone e senha fornecidos
        """
        phone_number, password, extra_fields = self._validate_user_data(phone_number, password, **extra_fields)

        # Define valores padrão para campos de permissão
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)

        # Cria o usuário
        user = self.model(phone_number=phone_number, username=str(phone_number), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        """
        Cria e salva um superusuário com o telefone e senha fornecidos
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'SUPER_ADMIN')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser deve ter is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser deve ter is_superuser=True.')

        return self.create_user(phone_number, password, **extra_fields)

    def create_admin_user(self, phone_number, password=None, **extra_fields):
        """
        Cria e salva um usuário administrador
        """
        extra_fields.setdefault('role', 'ADMIN')
        return self.create_user(phone_number, password, **extra_fields)

    def create_manager_user(self, phone_number, password=None, **extra_fields):
        """
        Cria e salva um usuário gerente
        """
        extra_fields.setdefault('role', 'MANAGER')
        return self.create_user(phone_number, password, **extra_fields)

    def create_employee_user(self, phone_number, password=None, **extra_fields):
        """
        Cria e salva um usuário funcionário
        """
        extra_fields.setdefault('role', 'EMPLOYEE')
        return self.create_user(phone_number, password, **extra_fields)

    def create_building_admin(self, phone_number, password=None, **extra_fields):
        """
        Cria e salva um administrador de condomínio
        """
        extra_fields.setdefault('role', 'BUILDING_ADMIN')
        return self.create_user(phone_number, password, **extra_fields)

    def create_unit_user(self, phone_number, password=None, **extra_fields):
        """
        Cria e salva um usuário de unidade (morador)
        """
        extra_fields.setdefault('role', 'UNIT_USER')
        return self.create_user(phone_number, password, **extra_fields)



class User(AbstractUser):
    # UUID primary key for scalability and security
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Remove first_name, last_name, and email fields from AbstractUser
    first_name = None
    last_name = None
    email = None

    # Keep username field but make it non-unique since we use phone_number as the primary identifier
    username = models.CharField(max_length=150)
    phone_number = PhoneNumberField(unique=True, region="BR")
    login_ips = models.TextField(blank=True, null=True, verbose_name="Login IP Addresses")
    
    # Device fingerprinting and security tracking
    device_fingerprints = models.TextField(blank=True, null=True, verbose_name="Device Fingerprints")
    last_password_change = models.DateTimeField(default=timezone.now, verbose_name="Last Password Change")

    class Role(models.TextChoices):
        SUPER_ADMIN    = "SUPER_ADMIN",    "Super Admin"
        ADMIN          = "ADMIN",          "Admin"
        MANAGER        = "MANAGER",        "Manager"
        EMPLOYEE       = "EMPLOYEE",       "Employee"
        BUILDING_ADMIN = "BUILDING_ADMIN", "Building Admin"
        UNIT_USER      = "UNIT_USER",      "Unit User"

    role = models.CharField(
        max_length=15,                    # "BUILDING_ADMIN" tem 13 caracteres
        choices=Role.choices,
        default=Role.UNIT_USER,
    )

    USERNAME_FIELD  = "phone_number"
    REQUIRED_FIELDS = []                  # sem username

    objects = UserManager()

    # ---------- conveniência --------------
    @property
    def is_internal(self) -> bool:
        return self.role in {
            self.Role.SUPER_ADMIN,
            self.Role.ADMIN,
            self.Role.MANAGER,
            self.Role.EMPLOYEE,
        }

    @property
    def is_property_admin(self) -> bool:
        return self.role == self.Role.BUILDING_ADMIN

    @property
    def is_unit_user(self) -> bool:
        return self.role == self.Role.UNIT_USER

    def add_login_ip(self, ip_address):
        """
        Add an IP address to the login history
        """
        if not ip_address:
            return

        ips = []
        if self.login_ips:
            try:
                ips = json.loads(self.login_ips)
            except json.JSONDecodeError:
                ips = []

        # Add the new IP if it's not already in the list
        if ip_address not in ips:
            ips.append(ip_address)

        # Store as JSON string
        self.login_ips = json.dumps(ips)
        self.save(update_fields=['login_ips'])

    def get_login_ips(self):
        """
        Get the list of login IP addresses
        """
        if not self.login_ips:
            return []

        try:
            return json.loads(self.login_ips)
        except json.JSONDecodeError:
            return []

    def add_device_fingerprint(self, fingerprint):
        """
        Add a device fingerprint to the history
        """
        if not fingerprint:
            return

        fingerprints = []
        if self.device_fingerprints:
            try:
                fingerprints = json.loads(self.device_fingerprints)
            except json.JSONDecodeError:
                fingerprints = []

        # Convert fingerprint to string if it's a UUID
        fingerprint_str = str(fingerprint)

        # Add the new fingerprint if it's not already in the list
        if fingerprint_str not in fingerprints:
            fingerprints.append(fingerprint_str)

        # Store as JSON string
        self.device_fingerprints = json.dumps(fingerprints)
        self.save(update_fields=['device_fingerprints'])

    def get_device_fingerprints(self):
        """
        Get the list of device fingerprints
        """
        if not self.device_fingerprints:
            return []

        try:
            return json.loads(self.device_fingerprints)
        except json.JSONDecodeError:
            return []

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"


class UserProfile(models.Model):
    """
    Extended profile information for users.
    Stores additional personal identification data.
    """
    # UUID primary key for scalability and security
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    full_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Full Name")
    gov_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="Gov ID Number")
    gov_id_state = models.CharField(max_length=50, blank=True, null=True, verbose_name="Gov ID State")
    tax_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="Gov Tax ID")
    cpf_cnpj = models.CharField(max_length=20, blank=True, null=True, verbose_name="CPF/CNPJ")
    nationality = models.CharField(max_length=100, blank=True, null=True)
    birthday = models.DateField(blank=True, null=True, verbose_name="Date of Birth")
    marital_status = models.CharField(max_length=50, blank=True, null=True, verbose_name="Estado Civil")
    profession = models.CharField(max_length=100, blank=True, null=True, verbose_name="Profissão")
    default_address_id = models.IntegerField(blank=True, null=True, verbose_name="Default Address ID")
    date_completed = models.DateTimeField(blank=True, null=True, verbose_name="Date Completed")
    preferred_communication_email = models.BooleanField(default=False, verbose_name="Preferred Communication: Email")
    preferred_communication_sms = models.BooleanField(default=False, verbose_name="Preferred Communication: SMS")
    preferred_communication_whatsapp = models.BooleanField(default=False, verbose_name="Preferred Communication: WhatsApp")
    allow_marketing = models.BooleanField(default=True, verbose_name="Allow Marketing")
    who_created = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_profiles', verbose_name="Created By")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Created At")
    updated_at = models.DateTimeField(default=timezone.now, verbose_name="Updated At")
    creation_ip = models.CharField(max_length=45, blank=True, null=True, verbose_name="Creation IP")

    def __str__(self):
        return f"Profile for {self.user.email}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Create a UserProfile when a User is created
    """
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Save the UserProfile when the User is saved
    """
    # Check if profile exists, create it if it doesn't
    if not hasattr(instance, 'profile'):
        UserProfile.objects.create(user=instance)
    else:
        instance.profile.save()

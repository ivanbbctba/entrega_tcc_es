from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm, AuthenticationForm
from django.contrib.auth import get_user_model, authenticate
from django.utils import timezone
from phonenumber_field.formfields import PhoneNumberField
import phonenumbers
from .models import UserProfile

User = get_user_model()

class CustomUserCreationForm(UserCreationForm):
    """
    A form that creates a user with phone number instead of username/email.
    """
    phone_number = PhoneNumberField(
        region='BR',
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control bg-transparent', 
            'placeholder': '(00) 00000-0000',
            'data-inputmask': '"mask": "(99) 99999-9999"'
        })
    )

    class Meta:
        model = User
        fields = ('phone_number', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We need to keep the username field for database compatibility
        # but hide it from the form
        if 'username' in self.fields:
            self.fields['username'].required = False
            self.fields['username'].widget = forms.HiddenInput()

        # Add placeholders and classes to password fields
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control bg-transparent',
            'placeholder': 'Password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control bg-transparent',
            'placeholder': 'Repeat Password'
        })

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if phone_number:
            # Parse and validate Brazilian phone number
            try:
                parsed = phonenumbers.parse(str(phone_number), 'BR')
                if not phonenumbers.is_valid_number(parsed):
                    raise forms.ValidationError('Por favor, insira um número de telefone brasileiro válido.')
                
                # Check if phone number already exists
                if User.objects.filter(phone_number=phone_number).exists():
                    raise forms.ValidationError('Este número de telefone já está cadastrado.')
                    
            except phonenumbers.phonenumberutil.NumberParseException:
                raise forms.ValidationError('Por favor, insira um número de telefone brasileiro válido.')
        
        return phone_number

    def clean(self):
        cleaned_data = super().clean()
        phone_number = cleaned_data.get('phone_number')

        # Set username to phone number string for database compatibility
        if phone_number and 'username' in self.fields:
            cleaned_data['username'] = str(phone_number)

        return cleaned_data


class CustomAuthenticationForm(AuthenticationForm):
    """
    A custom authentication form that uses phone number instead of username.
    """
    phone_number = PhoneNumberField(
        region='BR',
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control bg-transparent', 
            'placeholder': '(00) 00000-0000',
            'data-inputmask': '"mask": "(99) 99999-9999"',
            'autofocus': True
        })
    )
    
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        # Remove the username field from the form
        del self.fields['username']
        
        # Style the password field
        self.fields['password'].widget.attrs.update({
            'class': 'form-control bg-transparent',
            'placeholder': 'Senha'
        })
    
    def clean(self):
        phone_number = self.cleaned_data.get('phone_number')
        password = self.cleaned_data.get('password')
        
        if phone_number and password:
            # Try to find user by phone number
            try:
                user = User.objects.get(phone_number=phone_number)
                # Set the username for authentication
                self.cleaned_data['username'] = user.username
                
                # Authenticate using username and password
                self.user_cache = authenticate(
                    self.request, 
                    username=user.username, 
                    password=password
                )
                if self.user_cache is None:
                    raise forms.ValidationError('Número de telefone ou senha inválidos.')
                else:
                    self.confirm_login_allowed(self.user_cache)
                    
            except User.DoesNotExist:
                raise forms.ValidationError('Número de telefone ou senha inválidos.')
        
        return self.cleaned_data


class UserProfileForm(forms.ModelForm):
    """
    Form for editing user profile information
    """
    email = forms.EmailField(
        max_length=254,
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control form-control-lg form-control-solid'})
    )


    class Meta:
        model = UserProfile
        fields = ('full_name', 'nationality', 'birthday', 'marital_status', 'profession', 'gov_id', 'gov_id_state', 'tax_id', 'cpf_cnpj', 
                 'preferred_communication_email', 'preferred_communication_sms', 'preferred_communication_whatsapp', 'allow_marketing')
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control form-control-lg form-control-solid'}),
            'nationality': forms.Select(attrs={'class': 'form-select form-select-solid'}),
            'birthday': forms.DateInput(attrs={'class': 'form-control form-control-lg form-control-solid', 'type': 'date'}),
            'marital_status': forms.Select(attrs={'class': 'form-select form-select-solid'}),
            'profession': forms.Select(attrs={'class': 'form-select form-select-solid'}),
            'gov_id': forms.TextInput(attrs={'class': 'form-control form-control-lg form-control-solid'}),
            'gov_id_state': forms.Select(attrs={'class': 'form-select form-select-solid w-100px'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control form-control-lg form-control-solid'}),
            'cpf_cnpj': forms.HiddenInput(),  # We'll handle this with our custom field
            'preferred_communication_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'preferred_communication_sms': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'preferred_communication_whatsapp': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allow_marketing': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Add Brazil state choices
        brazil_states = [
            ('', ''),
            ('AC', 'AC'),
            ('AL', 'AL'),
            ('AP', 'AP'),
            ('AM', 'AM'),
            ('BA', 'BA'),
            ('CE', 'CE'),
            ('DF', 'DF'),
            ('ES', 'ES'),
            ('GO', 'GO'),
            ('MA', 'MA'),
            ('MT', 'MT'),
            ('MS', 'MS'),
            ('MG', 'MG'),
            ('PA', 'PA'),
            ('PB', 'PB'),
            ('PR', 'PR'),
            ('PE', 'PE'),
            ('PI', 'PI'),
            ('RJ', 'RJ'),
            ('RN', 'RN'),
            ('RS', 'RS'),
            ('RO', 'RO'),
            ('RR', 'RR'),
            ('SC', 'SC'),
            ('SP', 'SP'),
            ('SE', 'SE'),
            ('TO', 'TO'),
        ]
        self.fields['gov_id_state'].widget.choices = brazil_states

        # Add nationalities in Portuguese
        nationalities = [
            ('Brasileiro', 'Brasileiro'),
            ('Afegão', 'Afegão'),
            ('Albanês', 'Albanês'),
            ('Alemão', 'Alemão'),
            ('Americano', 'Americano'),
            ('Andorrano', 'Andorrano'),
            ('Angolano', 'Angolano'),
            ('Antiguano', 'Antiguano'),
            ('Argentino', 'Argentino'),
            ('Armênio', 'Armênio'),
            ('Australiano', 'Australiano'),
            ('Austríaco', 'Austríaco'),
            ('Azerbaijano', 'Azerbaijano'),
            ('Bahamense', 'Bahamense'),
            ('Bangladeshi', 'Bangladeshi'),
            ('Barbadiano', 'Barbadiano'),
            ('Belga', 'Belga'),
            ('Belizenho', 'Belizenho'),
            ('Beninense', 'Beninense'),
            ('Bielorrusso', 'Bielorrusso'),
            ('Boliviano', 'Boliviano'),
            ('Bósnio', 'Bósnio'),
            ('Botsuanês', 'Botsuanês'),
            ('Britânico', 'Britânico'),
            ('Bruneíno', 'Bruneíno'),
            ('Búlgaro', 'Búlgaro'),
            ('Burquinês', 'Burquinês'),
            ('Burundês', 'Burundês'),
            ('Butanês', 'Butanês'),
            ('Cabo-verdiano', 'Cabo-verdiano'),
            ('Camaronês', 'Camaronês'),
            ('Cambojano', 'Cambojano'),
            ('Canadense', 'Canadense'),
            ('Catariano', 'Catariano'),
            ('Chadiano', 'Chadiano'),
            ('Chileno', 'Chileno'),
            ('Chinês', 'Chinês'),
            ('Cipriota', 'Cipriota'),
            ('Colombiano', 'Colombiano'),
            ('Comorense', 'Comorense'),
            ('Congolês', 'Congolês'),
            ('Coreano', 'Coreano'),
            ('Costa-riquenho', 'Costa-riquenho'),
            ('Croata', 'Croata'),
            ('Cubano', 'Cubano'),
            ('Dinamarquês', 'Dinamarquês'),
            ('Djiboutiano', 'Djiboutiano'),
            ('Dominicano', 'Dominicano'),
            ('Egípcio', 'Egípcio'),
            ('Emiradense', 'Emiradense'),
            ('Equatoriano', 'Equatoriano'),
            ('Eritreu', 'Eritreu'),
            ('Eslovaco', 'Eslovaco'),
            ('Esloveno', 'Esloveno'),
            ('Espanhol', 'Espanhol'),
            ('Estoniano', 'Estoniano'),
            ('Etíope', 'Etíope'),
            ('Fijiano', 'Fijiano'),
            ('Filipino', 'Filipino'),
            ('Finlandês', 'Finlandês'),
            ('Francês', 'Francês'),
            ('Gabonês', 'Gabonês'),
            ('Gambiano', 'Gambiano'),
            ('Ganês', 'Ganês'),
            ('Georgiano', 'Georgiano'),
            ('Granadino', 'Granadino'),
            ('Grego', 'Grego'),
            ('Guatemalteco', 'Guatemalteco'),
            ('Guianês', 'Guianês'),
            ('Guineano', 'Guineano'),
            ('Guineense', 'Guineense'),
            ('Haitiano', 'Haitiano'),
            ('Holandês', 'Holandês'),
            ('Hondurenho', 'Hondurenho'),
            ('Húngaro', 'Húngaro'),
            ('Iemenita', 'Iemenita'),
            ('Indiano', 'Indiano'),
            ('Indonésio', 'Indonésio'),
            ('Iraniano', 'Iraniano'),
            ('Iraquiano', 'Iraquiano'),
            ('Irlandês', 'Irlandês'),
            ('Islandês', 'Islandês'),
            ('Israelense', 'Israelense'),
            ('Italiano', 'Italiano'),
            ('Jamaicano', 'Jamaicano'),
            ('Japonês', 'Japonês'),
            ('Jordaniano', 'Jordaniano'),
            ('Kuwaitiano', 'Kuwaitiano'),
            ('Laosiano', 'Laosiano'),
            ('Lesotiano', 'Lesotiano'),
            ('Letão', 'Letão'),
            ('Libanês', 'Libanês'),
            ('Liberiano', 'Liberiano'),
            ('Líbio', 'Líbio'),
            ('Liechtensteiniano', 'Liechtensteiniano'),
            ('Lituano', 'Lituano'),
            ('Luxemburguês', 'Luxemburguês'),
            ('Macedônio', 'Macedônio'),
            ('Malaio', 'Malaio'),
            ('Malauiano', 'Malauiano'),
            ('Maldivo', 'Maldivo'),
            ('Malgaxe', 'Malgaxe'),
            ('Maliano', 'Maliano'),
            ('Maltês', 'Maltês'),
            ('Marfinense', 'Marfinense'),
            ('Marroquino', 'Marroquino'),
            ('Mauriciano', 'Mauriciano'),
            ('Mauritano', 'Mauritano'),
            ('Mexicano', 'Mexicano'),
            ('Moçambicano', 'Moçambicano'),
            ('Moldovo', 'Moldovo'),
            ('Monegasco', 'Monegasco'),
            ('Mongol', 'Mongol'),
            ('Montenegrino', 'Montenegrino'),
            ('Namibiano', 'Namibiano'),
            ('Nepalês', 'Nepalês'),
            ('Nicaraguense', 'Nicaraguense'),
            ('Nigeriano', 'Nigeriano'),
            ('Nigerino', 'Nigerino'),
            ('Norte-coreano', 'Norte-coreano'),
            ('Norueguês', 'Norueguês'),
            ('Neozelandês', 'Neozelandês'),
            ('Omani', 'Omani'),
            ('Palestino', 'Palestino'),
            ('Panamenho', 'Panamenho'),
            ('Papua', 'Papua'),
            ('Paquistanês', 'Paquistanês'),
            ('Paraguaio', 'Paraguaio'),
            ('Peruano', 'Peruano'),
            ('Polonês', 'Polonês'),
            ('Português', 'Português'),
            ('Queniano', 'Queniano'),
            ('Quirguiz', 'Quirguiz'),
            ('Romeno', 'Romeno'),
            ('Ruandês', 'Ruandês'),
            ('Russo', 'Russo'),
            ('Samoano', 'Samoano'),
            ('Salvadorenho', 'Salvadorenho'),
            ('Santa-lucense', 'Santa-lucense'),
            ('São-cristovense', 'São-cristovense'),
            ('São-marinense', 'São-marinense'),
            ('São-tomense', 'São-tomense'),
            ('São-vicentino', 'São-vicentino'),
            ('Seichelense', 'Seichelense'),
            ('Senegalês', 'Senegalês'),
            ('Sérvio', 'Sérvio'),
            ('Serra-leonês', 'Serra-leonês'),
            ('Singapuriano', 'Singapuriano'),
            ('Sírio', 'Sírio'),
            ('Somali', 'Somali'),
            ('Sri-lankês', 'Sri-lankês'),
            ('Suazi', 'Suazi'),
            ('Sudanês', 'Sudanês'),
            ('Sueco', 'Sueco'),
            ('Suíço', 'Suíço'),
            ('Sul-africano', 'Sul-africano'),
            ('Sul-coreano', 'Sul-coreano'),
            ('Surinamês', 'Surinamês'),
            ('Tailandês', 'Tailandês'),
            ('Taiwanês', 'Taiwanês'),
            ('Tajique', 'Tajique'),
            ('Tanzaniano', 'Tanzaniano'),
            ('Tcheco', 'Tcheco'),
            ('Timorense', 'Timorense'),
            ('Togolês', 'Togolês'),
            ('Tonganês', 'Tonganês'),
            ('Trinitário', 'Trinitário'),
            ('Tunisiano', 'Tunisiano'),
            ('Turco', 'Turco'),
            ('Turquemeno', 'Turquemeno'),
            ('Ucraniano', 'Ucraniano'),
            ('Ugandês', 'Ugandês'),
            ('Uruguaio', 'Uruguaio'),
            ('Uzbeque', 'Uzbeque'),
            ('Vanuatuense', 'Vanuatuense'),
            ('Vaticano', 'Vaticano'),
            ('Venezuelano', 'Venezuelano'),
            ('Vietnamita', 'Vietnamita'),
            ('Zambiano', 'Zambiano'),
            ('Zimbabuano', 'Zimbabuano'),
        ]
        self.fields['nationality'].widget = forms.Select(attrs={'class': 'form-select form-select-solid'})
        self.fields['nationality'].widget.choices = nationalities
        self.fields['nationality'].initial = 'Brasileiro'

        # Add marital status options in Portuguese
        marital_status_choices = [
            ('', 'Selecione o estado civil'),
            ('Solteiro(a)', 'Solteiro(a)'),
            ('Casado(a)', 'Casado(a)'),
            ('Divorciado(a)', 'Divorciado(a)'),
            ('Viúvo(a)', 'Viúvo(a)'),
            ('União Estável', 'União Estável'),
            ('Separado(a)', 'Separado(a)'),
        ]
        self.fields['marital_status'].widget.choices = marital_status_choices

        # Add profession options in Portuguese (more than 50 options)
        profession_choices = [
            ('', 'Selecione a profissão'),
            ('Administrador(a)', 'Administrador(a)'),
            ('Advogado(a)', 'Advogado(a)'),
            ('Agente de Viagens', 'Agente de Viagens'),
            ('Agrônomo(a)', 'Agrônomo(a)'),
            ('Analista de Sistemas', 'Analista de Sistemas'),
            ('Antropólogo(a)', 'Antropólogo(a)'),
            ('Arqueólogo(a)', 'Arqueólogo(a)'),
            ('Arquiteto(a)', 'Arquiteto(a)'),
            ('Artesão(ã)', 'Artesão(ã)'),
            ('Artista Plástico(a)', 'Artista Plástico(a)'),
            ('Assistente Social', 'Assistente Social'),
            ('Atleta Profissional', 'Atleta Profissional'),
            ('Atuário(a)', 'Atuário(a)'),
            ('Auditor(a)', 'Auditor(a)'),
            ('Auxiliar Administrativo(a)', 'Auxiliar Administrativo(a)'),
            ('Bancário(a)', 'Bancário(a)'),
            ('Bibliotecário(a)', 'Bibliotecário(a)'),
            ('Biólogo(a)', 'Biólogo(a)'),
            ('Biomédico(a)', 'Biomédico(a)'),
            ('Cabeleireiro(a)', 'Cabeleireiro(a)'),
            ('Chef de Cozinha', 'Chef de Cozinha'),
            ('Cientista da Computação', 'Cientista da Computação'),
            ('Cientista de Dados', 'Cientista de Dados'),
            ('Cientista Político(a)', 'Cientista Político(a)'),
            ('Comerciante', 'Comerciante'),
            ('Consultor(a)', 'Consultor(a)'),
            ('Contador(a)', 'Contador(a)'),
            ('Corretor(a) de Imóveis', 'Corretor(a) de Imóveis'),
            ('Corretor(a) de Seguros', 'Corretor(a) de Seguros'),
            ('Cozinheiro(a)', 'Cozinheiro(a)'),
            ('Dentista', 'Dentista'),
            ('Designer', 'Designer'),
            ('Designer de Interiores', 'Designer de Interiores'),
            ('Designer Gráfico(a)', 'Designer Gráfico(a)'),
            ('Economista', 'Economista'),
            ('Editor(a)', 'Editor(a)'),
            ('Educador(a) Físico(a)', 'Educador(a) Físico(a)'),
            ('Eletricista', 'Eletricista'),
            ('Enfermeiro(a)', 'Enfermeiro(a)'),
            ('Engenheiro(a) Agrônomo(a)', 'Engenheiro(a) Agrônomo(a)'),
            ('Engenheiro(a) Ambiental', 'Engenheiro(a) Ambiental'),
            ('Engenheiro(a) Civil', 'Engenheiro(a) Civil'),
            ('Engenheiro(a) de Alimentos', 'Engenheiro(a) de Alimentos'),
            ('Engenheiro(a) de Computação', 'Engenheiro(a) de Computação'),
            ('Engenheiro(a) de Produção', 'Engenheiro(a) de Produção'),
            ('Engenheiro(a) de Software', 'Engenheiro(a) de Software'),
            ('Engenheiro(a) Elétrico(a)', 'Engenheiro(a) Elétrico(a)'),
            ('Engenheiro(a) Mecânico(a)', 'Engenheiro(a) Mecânico(a)'),
            ('Engenheiro(a) Químico(a)', 'Engenheiro(a) Químico(a)'),
            ('Estatístico(a)', 'Estatístico(a)'),
            ('Farmacêutico(a)', 'Farmacêutico(a)'),
            ('Filósofo(a)', 'Filósofo(a)'),
            ('Físico(a)', 'Físico(a)'),
            ('Fisioterapeuta', 'Fisioterapeuta'),
            ('Fonoaudiólogo(a)', 'Fonoaudiólogo(a)'),
            ('Fotógrafo(a)', 'Fotógrafo(a)'),
            ('Geógrafo(a)', 'Geógrafo(a)'),
            ('Geólogo(a)', 'Geólogo(a)'),
            ('Gerente Comercial', 'Gerente Comercial'),
            ('Gerente de Marketing', 'Gerente de Marketing'),
            ('Gerente de Projetos', 'Gerente de Projetos'),
            ('Gerente de Recursos Humanos', 'Gerente de Recursos Humanos'),
            ('Gerente Financeiro(a)', 'Gerente Financeiro(a)'),
            ('Historiador(a)', 'Historiador(a)'),
            ('Jornalista', 'Jornalista'),
            ('Marketeiro(a)', 'Marketeiro(a)'),
            ('Matemático(a)', 'Matemático(a)'),
            ('Mecânico(a)', 'Mecânico(a)'),
            ('Médico(a)', 'Médico(a)'),
            ('Médico(a) Veterinário(a)', 'Médico(a) Veterinário(a)'),
            ('Meteorologista', 'Meteorologista'),
            ('Motorista', 'Motorista'),
            ('Músico(a)', 'Músico(a)'),
            ('Nutricionista', 'Nutricionista'),
            ('Oceanógrafo(a)', 'Oceanógrafo(a)'),
            ('Odontólogo(a)', 'Odontólogo(a)'),
            ('Pedagogo(a)', 'Pedagogo(a)'),
            ('Piloto', 'Piloto'),
            ('Policial', 'Policial'),
            ('Professor(a)', 'Professor(a)'),
            ('Programador(a)', 'Programador(a)'),
            ('Psicólogo(a)', 'Psicólogo(a)'),
            ('Publicitário(a)', 'Publicitário(a)'),
            ('Químico(a)', 'Químico(a)'),
            ('Radialista', 'Radialista'),
            ('Recepcionista', 'Recepcionista'),
            ('Relações Públicas', 'Relações Públicas'),
            ('Secretário(a)', 'Secretário(a)'),
            ('Segurança', 'Segurança'),
            ('Servidor(a) Público(a)', 'Servidor(a) Público(a)'),
            ('Sociólogo(a)', 'Sociólogo(a)'),
            ('Técnico(a) de Enfermagem', 'Técnico(a) de Enfermagem'),
            ('Técnico(a) de Informática', 'Técnico(a) de Informática'),
            ('Técnico(a) de Segurança do Trabalho', 'Técnico(a) de Segurança do Trabalho'),
            ('Técnico(a) em Contabilidade', 'Técnico(a) em Contabilidade'),
            ('Técnico(a) em Eletrônica', 'Técnico(a) em Eletrônica'),
            ('Técnico(a) em Mecânica', 'Técnico(a) em Mecânica'),
            ('Terapeuta Ocupacional', 'Terapeuta Ocupacional'),
            ('Tradutor(a)', 'Tradutor(a)'),
            ('Vendedor(a)', 'Vendedor(a)'),
            ('Zootecnista', 'Zootecnista'),
            ('Outro', 'Outro'),
        ]
        self.fields['profession'].widget.choices = profession_choices

        if user:
            self.fields['email'].initial = user.email

    def clean_cpf_cnpj(self):
        """
        Convert the toggle switch value to either "CPF" or "CNPJ"
        """
        cpf_cnpj_value = self.cleaned_data.get('cpf_cnpj')

        # The checkbox will be 'on' if checked (CNPJ) or not present if unchecked (CPF)
        if cpf_cnpj_value == 'on' or cpf_cnpj_value is True:
            return "CNPJ"
        else:
            return "CPF"

    def clean_tax_id(self):
        """
        Strip any non-numeric characters from the tax_id field
        """
        tax_id = self.cleaned_data.get('tax_id', '')

        # Remove any non-numeric characters (masks, etc.)
        if tax_id:
            tax_id = ''.join(c for c in tax_id if c.isdigit())

        return tax_id

    def save(self, user=None, commit=True):
        try:
            # Get the profile instance without saving it
            profile = super().save(commit=False)

            # Add more detailed logging
            print("Form save method called")
            print("Cleaned data:", self.cleaned_data)
            print("Instance before save:", profile.__dict__)

            if user:
                print("User before save:", user.__dict__)

                # Update user fields
                old_email = user.email
                new_email = self.cleaned_data.get('email')

                if old_email != new_email:
                    print(f"Updating email from {old_email} to {new_email}")
                    user.email = new_email

                    # Also update username since it's used for login
                    user.username = new_email

                if commit:
                    try:
                        user.save(update_fields=['email', 'username'])
                        print("User saved successfully")
                    except Exception as e:
                        print(f"Error saving user: {e}")
                        raise

            # Save the profile
            if commit:
                try:
                    profile.save()
                    print("Profile saved successfully")
                    print("Profile after save:", profile.__dict__)
                except Exception as e:
                    print(f"Error saving profile: {e}")
                    raise

            return profile

        except Exception as e:
            print(f"Exception in UserProfileForm.save: {e}")
            import traceback
            traceback.print_exc()
            raise


class CustomPasswordChangeForm(PasswordChangeForm):
    """
    Custom password change form with styling for the project's UI.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add styling to the form fields
        self.fields['old_password'].widget.attrs.update({
            'class': 'form-control form-control-lg form-control-solid',
            'id': 'currentpassword'
        })
        self.fields['new_password1'].widget.attrs.update({
            'class': 'form-control form-control-lg form-control-solid',
            'id': 'newpassword'
        })
        self.fields['new_password2'].widget.attrs.update({
            'class': 'form-control form-control-lg form-control-solid',
            'id': 'confirmpassword'
        })

    def clean_old_password(self):
        """
        Validate the old password.
        """
        old_password = self.cleaned_data.get('old_password')
        if not self.user.check_password(old_password):
            raise forms.ValidationError(
                "Your old password was entered incorrectly. Please enter it again."
            )
        return old_password

    def save(self, commit=True):
        """
        Save the new password and update the last_password_change timestamp.
        """
        password = self.cleaned_data["new_password1"]
        self.user.set_password(password)
        
        # Update the last_password_change timestamp
        self.user.last_password_change = timezone.now()
        
        if commit:
            self.user.save(update_fields=['password', 'last_password_change'])
        return self.user

from django import forms
from .models import Tamu, Kunjungan, Pegawai, Message
import hashlib


class TamuLoginForm(forms.Form):
    username = forms.CharField(
        label="Email / NIK",
        widget=forms.TextInput(attrs={'placeholder': 'Masukkan email atau NIK 16 digit'})
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Masukkan password Anda'})
    )

    GENERIC_ERROR = "Email/NIK atau password salah."

    def clean(self):
        cleaned = super().clean()
        username = cleaned.get('username')
        password = cleaned.get('password')
        
        if username and password:
            from django.contrib.auth.hashers import check_password
            from .security_utils import classify_identifier

            kind, normalized = classify_identifier(username)
            qs = Tamu.objects.filter(account_status='active')
            if kind == 'email':
                qs = qs.filter(email__iexact=normalized)
            elif kind == 'nik':
                qs = qs.filter(nik=normalized)
            else:
                qs = qs.none()
            matches = list(qs[:2])
            if len(matches) == 1 and check_password(password, matches[0].password):
                self.tamu = matches[0]
            else:
                raise forms.ValidationError(self.GENERIC_ERROR)
        return cleaned


class TamuRegisterForm(forms.Form):
    name = forms.CharField(
        max_length=255, label="Nama Lengkap",
        widget=forms.TextInput(attrs={'placeholder': 'Masukkan nama sesuai identitas'})
    )
    nik = forms.CharField(
        min_length=16, max_length=16, label="NIK (Nomor Induk Kependudukan)",
        widget=forms.TextInput(attrs={'placeholder': '16 digit nomor NIK'}),
        error_messages={
            'min_length': 'NIK harus tepat 16 digit.',
            'max_length': 'NIK tidak boleh lebih dari 16 digit.',
            'required': 'Nomor NIK wajib diisi.'
        }
    )
    phone = forms.CharField(
        max_length=20, label="Nomor Telepon",
        widget=forms.TextInput(attrs={'placeholder': 'Contoh: 0812xxxx'})
    )
    instansi = forms.CharField(
        max_length=255, label="Instansi / Lembaga",
        widget=forms.TextInput(attrs={'placeholder': 'Nama organisasi asal'})
    )
    purpose = forms.CharField(
        label="Tujuan Kunjungan", required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Jelaskan secara singkat keperluan kunjungan Anda'})
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'placeholder': 'nama@email.com'})
    )
    password1 = forms.CharField(
        label="Password", min_length=8,
        widget=forms.PasswordInput(attrs={'placeholder': 'Minimal 8 karakter'})
    )
    password2 = forms.CharField(
        label="Konfirmasi Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Ulangi password'})
    )

    def clean_nik(self):
        nik = self.cleaned_data.get('nik')
        if not nik.isdigit():
            raise forms.ValidationError("NIK hanya boleh berisi angka.")
        if len(nik) != 16:
            raise forms.ValidationError("NIK harus berjumlah tepat 16 digit.")
        return nik

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if Tamu.objects.filter(email=email).exists():
            raise forms.ValidationError("Email ini sudah terdaftar.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', "Password tidak cocok.")
        return cleaned

    def save(self):
        data = self.cleaned_data
        from django.contrib.auth.hashers import make_password
        hashed = make_password(data['password1'])
        tamu = Tamu.objects.create(
            name=data['name'],
            email=data['email'],
            phone=data['phone'],
            nik=data.get('nik'),
            instansi=data.get('instansi'),
            password=hashed,
            registration_type='manual',
            account_status='active',
        )
        return tamu


class TamuPasswordResetForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'placeholder': 'Masukkan email terdaftar'})
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not Tamu.objects.filter(email=email, account_status='active').exists():
            raise forms.ValidationError("Email ini tidak terdaftar atau akun tidak aktif.")
        return email


class TamuSetPasswordForm(forms.Form):
    password1 = forms.CharField(
        label="Password Baru", min_length=8,
        widget=forms.PasswordInput(attrs={'placeholder': 'Minimal 8 karakter'})
    )
    password2 = forms.CharField(
        label="Konfirmasi Password Baru",
        widget=forms.PasswordInput(attrs={'placeholder': 'Ulangi password baru'})
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', "Password tidak cocok.")
        return cleaned


class KunjunganForm(forms.ModelForm):
    pegawai = forms.ModelChoiceField(
        queryset=Pegawai.objects.filter(account_status='active').order_by('department', 'name'),
        label="Pegawai yang Dituju",
        empty_label="-- Pilih Pegawai --",
        required=True,
    )
    purpose = forms.CharField(
        max_length=500, label="Keperluan / Tujuan",
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Tuliskan keperluan kunjungan Anda...'})
    )
    arrival_time = forms.DateTimeField(
        label="Tanggal & Waktu Kedatangan",
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )
    departure_time = forms.DateTimeField(
        label="Perkiraan Waktu Pulang",
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        required=False,
    )
    notes = forms.CharField(
        label="Catatan Tambahan",
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
    )

    class Meta:
        model = Kunjungan
        fields = ['pegawai', 'purpose', 'arrival_time', 'departure_time', 'notes']

    def clean(self):
        cleaned = super().clean()
        arrival = cleaned.get('arrival_time')
        departure = cleaned.get('departure_time')

        if arrival:
            from .validators import validate_kunjungan_schedule
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_kunjungan_schedule(
                    arrival_time=arrival,
                    departure_time=departure,
                    instance=self.instance,
                    is_admin=False,
                    is_import=False
                )
            except DjangoValidationError as e:
                if hasattr(e, 'error_dict'):
                    for field, error_list in e.error_dict.items():
                        for err in error_list:
                            self.add_error(field, err)
                elif hasattr(e, 'message'):
                    self.add_error('arrival_time', e.message)
                else:
                    self.add_error('arrival_time', str(e))
        return cleaned


class PesanForm(forms.Form):
    subject = forms.CharField(
        max_length=500, label="Subjek",
        widget=forms.TextInput(attrs={'placeholder': 'Subjek pesan...'})
    )
    content = forms.CharField(
        label="Isi Pesan",
        widget=forms.Textarea(attrs={'rows': 5, 'placeholder': 'Tulis pesan Anda di sini...'})
    )


# ============================================================================
# APPROVAL WORKFLOW FORMS
# ============================================================================

class KunjunganCreateForm(forms.ModelForm):
    """Form untuk Tamu membuat request kunjungan baru."""
    
    pegawai = forms.ModelChoiceField(
        queryset=Pegawai.objects.filter(account_status='active').select_related('department_rel'),
        label="Pegawai yang Dituju",
        empty_label="-- Pilih Pegawai --",
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    purpose = forms.CharField(
        max_length=500,
        label="Keperluan / Tujuan",
        widget=forms.Textarea(attrs={
            'rows': 4,
            'class': 'form-control',
            'placeholder': 'Jelaskan tujuan kunjungan Anda...'
        })
    )
    
    arrival_time = forms.DateTimeField(
        label="Tanggal & Waktu Kedatangan",
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local',
            'class': 'form-control'
        })
    )
    
    class Meta:
        model = Kunjungan
        fields = ['pegawai', 'purpose', 'arrival_time']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Group pegawai by department dalam dropdown
        self.fields['pegawai'].queryset = self.fields['pegawai'].queryset.order_by('department_rel__nama', 'name')
    
    def clean_arrival_time(self):
        """Validasi arrival time harus di masa depan."""
        from django.utils import timezone
        arrival = self.cleaned_data.get('arrival_time')
        if arrival and arrival < timezone.now():
            raise forms.ValidationError("Waktu kedatangan harus di masa depan")
        return arrival


class PegawaiResponseForm(forms.Form):
    """Form untuk Pegawai approve atau reject kunjungan."""
    
    ACTION_CHOICES = [
        ('approve', 'Setujui'),
        ('reject', 'Tolak'),
        ('reschedule', 'Usulkan Jadwal Ulang'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Keputusan"
    )
    
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'class': 'form-control',
            'placeholder': 'Wajib diisi jika menolak atau jadwal ulang. Jelaskan alasan/pesan...'
        }),
        label="Alasan / Pesan"
    )

    reschedule_time = forms.DateTimeField(
        required=False,
        label="Usulan Waktu Baru",
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local',
            'class': 'form-control'
        })
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'form-control',
            'placeholder': 'Catatan tambahan (opsional)'
        }),
        label="Catatan"
    )
    
    def clean(self):
        cleaned = super().clean()
        action = cleaned.get('action')
        rejection_reason = cleaned.get('rejection_reason', '').strip()
        reschedule = cleaned.get('reschedule_time')
        
        if action in ['reject', 'reschedule'] and not rejection_reason:
            self.add_error('rejection_reason', 'Alasan/pesan wajib diisi.')
            
        if action == 'reschedule' and not reschedule:
            self.add_error('reschedule_time', 'Usulan waktu baru wajib diisi.')
            
        return cleaned

class PegawaiReportForm(forms.Form):
    """Form untuk Laporan/Catatan Hasil Pertemuan oleh Pegawai."""
    content = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'class': 'form-control',
            'placeholder': 'Tuliskan laporan hasil rapat atau pertemuan di sini...'
        }),
        label="Laporan Hasil Pertemuan"
    )


class AdminForwardForm(forms.Form):
    """Form untuk Admin meneruskan kunjungan ke Pegawai."""
    
    pegawai = forms.ModelChoiceField(
        queryset=Pegawai.objects.filter(account_status='active').select_related('department_rel'),
        label="Teruskan ke Pegawai",
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    admin_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'form-control',
            'placeholder': 'Catatan internal untuk Admin (tidak terlihat oleh Tamu)'
        }),
        label="Catatan Admin"
    )
    
    def __init__(self, *args, current_pegawai=None, **kwargs):
        super().__init__(*args, **kwargs)
        if current_pegawai:
            self.fields['pegawai'].initial = current_pegawai
        self.fields['pegawai'].queryset = self.fields['pegawai'].queryset.order_by('department_rel__nama', 'name')


class AdminACCForm(forms.Form):
    """Form untuk Admin memberikan ACC final."""
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'form-control',
            'placeholder': 'Catatan ACC (opsional)'
        }),
        label="Catatan"
    )

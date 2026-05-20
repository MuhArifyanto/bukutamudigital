from django import forms
from .models import Tamu, Kunjungan, Pegawai, Message
import hashlib


class TamuLoginForm(forms.Form):
    username = forms.CharField(
        label="Nama Lengkap / Email",
        widget=forms.TextInput(attrs={'placeholder': 'Masukkan nama atau email'})
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Masukkan password Anda'})
    )

    def clean(self):
        cleaned = super().clean()
        username = cleaned.get('username')
        password = cleaned.get('password')
        
        if username and password:
            try:
                from django.db.models import Q
                from django.contrib.auth.hashers import check_password
                
                tamu = Tamu.objects.get(
                    Q(name=username) | Q(email=username),
                    account_status='active'
                )
                if check_password(password, tamu.password):
                    self.tamu = tamu
                else:
                    raise forms.ValidationError("Nama/Email atau Password salah.")
            except Tamu.DoesNotExist:
                raise forms.ValidationError("Nama/Email atau Password salah.")
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
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )
    departure_time = forms.DateTimeField(
        label="Perkiraan Waktu Pulang",
        input_formats=['%Y-%m-%dT%H:%M'],
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
        if arrival and departure and departure <= arrival:
            self.add_error('departure_time', "Waktu pulang harus setelah waktu kedatangan.")
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

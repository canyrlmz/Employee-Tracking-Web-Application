from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecretkey123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///personel.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Modeller
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tc = db.Column(db.String(11), unique=True, nullable=False)
    sifre_hash = db.Column(db.String(128), nullable=False)
    orijinal_sifre = db.Column(db.String(128))  # Orijinal şifreyi saklamak için
    rol = db.Column(db.String(10), default='personel')  # 'admin' veya 'personel'
    ad = db.Column(db.String(100), nullable=False)
    departman = db.Column(db.String(100), nullable=False)
    durum = db.Column(db.String(50), default='Aktif')  # Varsayılan olarak Aktif
    ise_giris = db.Column(db.Date, nullable=True)
    sozlesme_bitis = db.Column(db.Date, nullable=True)
    haftalik_calisma_saati = db.Column(db.Integer, default=40)
    aylik_calisma_saati = db.Column(db.Integer, default=160)
    kalan_izin_gunu = db.Column(db.Integer, default=0)  # Başlangıçta 0, yenilenir

class Izin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    baslangic_tarihi = db.Column(db.Date, nullable=False)
    bitis_tarihi = db.Column(db.Date, nullable=False)
    durum = db.Column(db.String(20), default='Bekliyor')  # Bekliyor, Onaylandi, Reddedildi

class SistemAyarlari(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    izin_orani = db.Column(db.Float, default=0.1)  # Aylık saatin %10'u izin günü

# Veritabanını oluştur ve varsayılan admin ekle
with app.app_context():
    db.create_all()
    if not User.query.filter_by(rol='admin').first():
        admin_sifre = generate_password_hash('admin123')
        admin = User(tc='00000000000', sifre_hash=admin_sifre, rol='admin', ad='Admin', departman='Yönetim', durum='Aktif', ise_giris=datetime.now().date())
        db.session.add(admin)
        db.session.commit()
    if not SistemAyarlari.query.first():
        ayar = SistemAyarlari()
        db.session.add(ayar)
        db.session.commit()

def izin_yenile(user):
    if user is None or user.ise_giris is None:
        return  # Hata önleme, None ise işlem yapma
    simdi = datetime.now().date()
    yil_baslangic = datetime(simdi.year, 1, 1).date()
    if yil_baslangic > user.ise_giris or user.kalan_izin_gunu == 0:
        ayar = SistemAyarlari.query.first()
        user.kalan_izin_gunu = int(user.aylik_calisma_saati * ayar.izin_orani)
        db.session.commit()

@app.route('/', methods=['GET', 'POST'])
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    user_id = session.get('user_id')
    if user_id is None:
        flash('Oturum bilgisi eksik, lütfen tekrar giriş yapın.', 'danger')
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    if user is None:
        flash('Kullanıcı bulunamadı, lütfen admin ile iletişime geçin.', 'danger')
        return redirect(url_for('login'))
    izin_yenile(user)
    if user.rol == 'admin':
        users = User.query.all()
        izinler = Izin.query.all()
        izinler_ile_ad = [(izin, User.query.get(izin.user_id).ad if User.query.get(izin.user_id) else 'Bilinmeyen') for izin in izinler]
        ayar = SistemAyarlari.query.first()
        if request.method == 'POST':
            tc = request.form.get('tc')
            ad = request.form.get('ad')
            departman = request.form.get('departman')
            if not all([tc, ad, departman]):
                flash('Tüm alanlar doldurulmalı! (TC, Ad, Departman)', 'danger')
            elif User.query.filter_by(tc=tc).first():
                flash('Bu TC zaten kayıtlı!', 'danger')
            else:
                sifre = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                sifre_hash = generate_password_hash(sifre)
                yeni_user = User(tc=tc, sifre_hash=sifre_hash, orijinal_sifre=sifre, rol='personel', ad=ad, departman=departman, durum='Aktif', ise_giris=datetime.now().date())
                db.session.add(yeni_user)
                db.session.commit()
                flash(f'{ad} eklendi. TC: {tc}, Şifre: {sifre}', 'success')
        return render_template('index.html', users=users, izinler=izinler_ile_ad, ayar=ayar, kalan_izin=user.kalan_izin_gunu, rol=user.rol)
    else:
        izinler = Izin.query.filter_by(user_id=user_id).all()
        izinler_ile_ad = [(izin, user.ad) for izin in izinler]
        return render_template('index.html', users=[user], izinler=izinler_ile_ad, kalan_izin=user.kalan_izin_gunu, rol=user.rol)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        tc = request.form['tc']
        sifre = request.form['sifre']
        user = User.query.filter_by(tc=tc).first()
        if user and check_password_hash(user.sifre_hash, sifre):
            session['logged_in'] = True
            session['user_id'] = user.id
            session['rol'] = user.rol
            flash('Giriş başarılı!', 'success')
            return redirect(url_for('index'))
        else:
            flash('TC veya şifre yanlış!', 'danger')
    return render_template('login.html')

@app.route('/kayit', methods=['GET', 'POST'])
def kayit():
    if request.method == 'POST':
        tc = request.form['tc']
        sifre = request.form['sifre']
        ad = request.form['ad']
        departman = request.form['departman']
        if User.query.filter_by(tc=tc).first():
            flash('Bu TC zaten kayıtlı!', 'danger')
            return redirect(url_for('kayit'))
        sifre_hash = generate_password_hash(sifre)
        yeni_user = User(tc=tc, sifre_hash=sifre_hash, rol='personel', ad=ad, departman=departman, durum='Aktif', ise_giris=datetime.now().date())
        db.session.add(yeni_user)
        db.session.commit()
        flash('Kayıt başarılı! Giriş yapabilirsiniz.', 'success')
        return redirect(url_for('login'))
    return render_template('kayit.html')

@app.route('/guncelle_calisma_saat/<int:id>', methods=['POST'])
def guncelle_calisma_saat(id):
    if not session.get('logged_in') or session.get('rol') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(id)
    user.haftalik_calisma_saati = int(request.form['haftalik'])
    user.aylik_calisma_saati = int(request.form['aylik'])
    db.session.commit()
    flash('Çalışma saatleri güncellendi!', 'success')
    return redirect(url_for('index'))

@app.route('/guncelle_izin_orani', methods=['POST'])
def guncelle_izin_orani():
    if not session.get('logged_in') or session.get('rol') != 'admin':
        return redirect(url_for('login'))
    ayar = SistemAyarlari.query.first()
    ayar.izin_orani = float(request.form['izin_orani'])
    db.session.commit()
    flash('İzin oranı güncellendi!', 'success')
    return redirect(url_for('index'))

@app.route('/izin_talep', methods=['GET', 'POST'])
def izin_talep():
    if not session.get('logged_in') or session.get('rol') == 'admin':
        return redirect(url_for('login'))
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    izin_yenile(user)
    if request.method == 'POST':
        baslangic = datetime.strptime(request.form['baslangic'], '%Y-%m-%d').date()
        bitis = datetime.strptime(request.form['bitis'], '%Y-%m-%d').date()
        gun_sayisi = (bitis - baslangic).days + 1
        if gun_sayisi > user.kalan_izin_gunu:
            flash('Yeterli izin gününüz yok!', 'danger')
        else:
            yeni_izin = Izin(user_id=user_id, baslangic_tarihi=baslangic, bitis_tarihi=bitis)
            db.session.add(yeni_izin)
            db.session.commit()
            flash('İzin talebiniz gönderildi!', 'success')
        return redirect(url_for('index'))
    return render_template('izin_talep.html', kalan_izin=user.kalan_izin_gunu)

@app.route('/izin_yonet/<int:id>/<string:action>')
def izin_yonet(id, action):
    if not session.get('logged_in') or session.get('rol') != 'admin':
        return redirect(url_for('login'))
    izin = Izin.query.get_or_404(id)
    if action == 'onayla':
        gun_sayisi = (izin.bitis_tarihi - izin.baslangic_tarihi).days + 1
        user = User.query.get(izin.user_id)
        if gun_sayisi <= user.kalan_izin_gunu:
            user.kalan_izin_gunu -= gun_sayisi
            izin.durum = 'Onaylandi'
            flash('İzin onaylandı!', 'success')
        else:
            flash('Personelin yeterli izni yok!', 'danger')
    elif action == 'red':
        izin.durum = 'Reddedildi'
        flash('İzin reddedildi!', 'danger')
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/sil/<int:id>')
def sil(id):
    if not session.get('logged_in') or session.get('rol') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    flash(f'Personel {user.ad} başarıyla silindi!', 'success')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Çıkış yaptınız.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
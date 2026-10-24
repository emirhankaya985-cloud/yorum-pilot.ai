# YorumPilot AI — Free Neon PostgreSQL bağlantısı

## Neden Neon?
Render Free web servislerinde SQLite dosyası yeniden başlatma/uyku/dağıtım sırasında kaybolur. CareerHunter AI'ye ait Render Free PostgreSQL veritabanı **kesinlikle** paylaşılmamalıdır.

## Bağlantı yapılmadan önce
- Yalnızca ayrı bir Neon Free projesi oluştur: `yorumpilot-ai`; bölgeyi mümkünse Frankfurt seç.
- Herhangi bir ücretli plan, otomatik ücret yükseltme, kart bilgisi gerektiren özellik veya ödeme etkinleştirme yapma.
- Bağlantı dizesini GitHub'a, ChatGPT sohbetine, loglara, commit'e veya frontend'e yazma.
- API URL'sini değil, PostgreSQL SSL içeren bağlantı URL'sini kullan.

## Render bağlantısı
- [API Render ayarları](https://dashboard.render.com/web/srv-dbe5b6jncjis73e79cp0/env)
- `DATABASE_URL`: Neon panelindeki bağlantı URI'sini Render secret environment variable olarak tanımla.
- `APP_ENV=production`, `GOOGLE_MODE=mock`, `AI_PROVIDER=rules` korunmalıdır.
- Deploy sırasında Dockerfile `alembic upgrade head` çalıştırıp tablo şemasını oluşturur.
- `/api/system/status` `database_mode=external_postgresql` döndürmelidir.
- Ayrı demo hesap kaydı oluştur, servis yeniden başlatıldıktan sonra demo hesap ve yorumların korunup korunmadığını doğrula.

## Güvenlik
- PostgreSQL bağlantısı server-side kalır; asla `NEXT_PUBLIC_*` veya tarayıcıya taşınmaz.
- Uygulama şu an üretim hazır değildir. Gerçek Google yorumu, ödeme/abonelik, müşteriye ait PII kaydetme.
- Neon Free planı kullanım ve kaynak limitleri zaman içinde değişebilir. Limitleri proje panelinden izle.
- Canlı bildirim ve AI çağrısı başlamadan önce kullanıcı yetki ve veri işleme kuralları tamamlanmalıdır.

## Hazır olma koşulları
1. Neon Free proje kimliği oluşturuldu (farklı müşteri/proje DB'si değil)
2. `DATABASE_URL` Render secret olarak yüklendi
3. Migration başarılı
4. Render deploy LIVE
5. Signup/login/draft/publish simulation uçtan uca PASS
6. Render restart sonrası aynı veriye yeniden erişim PASS

Şu koşulların tamamı kanıtlanmadan `Neon bağlı` denmemelidir.

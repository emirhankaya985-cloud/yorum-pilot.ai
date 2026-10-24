# YorumPilot AI 🚀

Google Business Profile yorumları için planlanan abonelik tabanlı SaaS ürününün **offline çalışan ilk dikey dilimi**. Bu sürüm gerçek Google yorumlarını okumaz, gerçek LLM kullanmaz ve hiçbir Google cevabı yayımlamaz.

## Durum

- ✅ FastAPI API, üyelik/kayıt, imzalı oturum çerezi, CSRF koruması
- ✅ PostgreSQL uyumlu SQLAlchemy modelleri ve Alembic başlangıç migration'ı
- ✅ Çok müşterili veri ayrımı, roller (owner/admin/editor/viewer) ve zorunlu backend kontrolleri
- ✅ Tamamen sentetik yorumlarla demo, offline kural tabanlı analiz ve yanıt taslağı
- ✅ Taslak düzenleme, yeniden üretme, açık onay, idempotent **yalnızca demo** yayımlama simülasyonu
- ✅ 28 günlük önbellek süre sınırı, süresi dolan veriye erişimin engellenmesi, temizleme aracı (servis açıkken başlangıçta ve her 6 saatte otomatik temizleme)
- ✅ Responsive Next.js 16.4.3 landing, giriş/kayıt, gerçek API bağlantılı dashboard, yorum editörü, ayarlar
- ✅ 24 backend otomatik testi, CI workflow, Docker Compose, Render blueprint taslağı
- ⏳ Google API erişimi ve OAuth, Pub/Sub, gerçek yayımlama: ETKİN DEĞİL
- ✅ Telegram/ntfy taşıyıcı yardımcıları ve OAuth PKCE/state araçları (offline testli; hesap eşleştirme/gerçek entegrasyon devre dışı)
- ⏳ Gerçek Telegram/ntfy bağlantısı, LLM provider, abonelik tahsilatı, hesap silme, çoklu kullanıcı daveti: UYGULANMADI
- ⏳ Rate limiting, e-posta doğrulama, kapsamlı penetrasyon testi ve canlı yük testi: UYGULANMADI

**Bu bir ticari satışa hazır/production-ready ürün değildir.** Demo verileri gerçek müşteri verisi değildir.

## Yerel başlatma

Docker Desktop ile:

```sh
docker compose up --build
```

- Web: http://localhost:3000
- API sağlık: http://localhost:8000/healthz
- API dokümanı: http://localhost:8000/docs

Docker olmadan:

```sh
cd backend
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Başka terminal:

```sh
cd frontend
npm install
npm run dev
```

`APP_ENV=production` kullanılırsa `SECRET_KEY` güçlü olmalıdır ve migration uygulanmalıdır. `GOOGLE_MODE` yalnızca `mock` ve `pending` değerlerini kabul eder. Üçüncü taraf API erişimini atlatmaya çalışan canlı mod yoktur.

## Test

```sh
cd backend
python -m pytest -q
```

```sh
cd frontend
npm install
npm run typecheck
npm run build
```

## Google uyumluluk

- Google kaynaklı veriler en fazla 30 takvim günü geçici saklanabilir; sistem güvenlik payıyla 28 gün uygular.
- İşletme sahibi adına Google'a yanıt göndermeden önce açık, spesifik yetki gerekir.
- SaaS ürününe API erişimi sağlayabilmek için Google'ın üçüncü taraf API kullanım kuralları ve müşteriye özgü proje gereklilikleri ayrıca hukuki/teknik olarak değerlendirilecektir.
- `docs/GOOGLE_COMPLIANCE.md` dosyasına bakın.

## Repository hedefi

`emirhankaya985-cloud/yorum-pilot.ai`

## Değişiklik kaydı

24 Ekim 2026 — İlk offline MVP. Bütün açık ve yapılmamış parçalar güvenli biçimde işaretlenmiştir.


## Ek güvenli demo altyapısı

- NVIDIA NIM draft sağlayıcısı kodu hazırdır; yalnızca sunucuya `AI_PROVIDER=nvidia` ve `NVIDIA_API_KEY` girilirse taslak yeniden üretme kullanır. Model varsayılan `openai/gpt-oss-20b`. Anahtar olmadan gerçek AI isteği yapılmaz.
- AI hata/429/bozuk cevap durumunda 503 üretilir ve mevcut taslak korunur. İnsan onayı olmadan gerçek Google yanıtı yayımlanmaz.
- Kayıt/giriş için tek süreçli demo hız sınırı; kritik müşteri operasyonları için dağıtık limit sistemi hâlâ gereklidir.
- Render Free SQLite kalıcı değildir. Ayrı Neon Free PostgreSQL yapılandırması yapılana kadar gerçek müşteri verisi girmeyin.

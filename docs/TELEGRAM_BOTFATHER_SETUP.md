# Telegram BotFather — YorumPilot AI / DEMO

YorumPilot AI'nin Telegram eşleştirmesi **güvenli, işletme bazlı, tek kullanımlık kod** üzerinden gerçekleşir. Canlı Google'a yayınlamaz.

## 1. BotFather (yalnızca bot sahibi)
1. https://t.me/BotFather sayfasını açıp `/newbot` gönder.
2. İsim: `YorumPilot AI | Bildirim Merkezi`
3. Username önerileri: `YorumPilotAI_Bot`, `YorumPilotNotifyBot`. Kullanılabilirlik BotFather tarafından kontrol edilir.
4. BotFather'ın verdiği tokenı **asla sohbete, GitHub'a, dosyaya veya public URL'ye yapıştırma**.
5. İsteğe bağlı: `/setdescription` ile: `YorumPilot AI: yorum bildirimi ve insan onaylı yanıt taslakları. Google'a otomatik cevap göndermez.`
6. İsteğe bağlı: `/setabouttext` ile: `YorumPilot AI • Yorum bildirimleri ve güvenli onay yönetimi.`
7. `/setjoingroups` -> Disable. Bot yalnızca özel sohbetleri eşleştirir. Inline mode gerekmiyor.

## 2. Render token bağlantısı
[Render API → Environment](https://dashboard.render.com/web/srv-dbe5b6jncjis73e79cp0/env)
Sunucu ortamına **tek değişken** ekle:
`TELEGRAM_BOT_TOKEN` = BotFather'ın özel tokenı.

Başka mevcut değişkenleri silme veya replace etme. Render değişiklikten sonra otomatik redeploy yapar.

Uygulama başlatılırken güvenli HTTPS webhook'u `setWebhook` ile otomatik kaydeder:
`https://yorumpilot-api.onrender.com/api/telegram/webhook`.
Webhook imzası uygulamanın **Render'da mevcut** `SECRET_KEY` değeriyle token üzerinden türetilir; ayrı gizli anahtar girmeye gerek yoktur.
Komutlar `getMe` ve `setMyCommands` ile otomatik ayarlanır.

## 3. Telegram hesabını web paneline bağla
1. https://yorumpilot-web.onrender.com adresinde demo hesabınla giriş yap.
2. Panel -> Ayarlar -> **Telegram hesabımı bağla**.
3. Açılan Telegram bot sohbetinde **Başlat** butonuna bas. Bağlama kodu 10 dakika geçerli ve tek kullanımlıktır.
4. Paneli yenile. **Telefonuma test bildirimi gönder** düğmesiyle sentetik yorum + Onayla/Reddet/Beklet butonlarını dene.

## 4. Butonların gerçek etkileri
- **Onayla**: yanıt taslağını onaylar; **Google'a GÖNDERMEZ**.
- **Reddet**: mevcut taslağı reddeder.
- **Beklet**: yorumu `deferred` durumuna getirir; panelde beklemeye devam eder.
- Callback yalnızca eşleştirilmiş Telegram özel sohbetinden, yetkili işletme sahibi/admin tarafından kabul edilir.
- Eski/tekrarlanan `update_id` olayları Neon tablosuyla engellenir.
- Bot yeni Google yorumlarını **henüz kendiliğinden çekmez**; Google Business Profile API erişimi ayrı fazdır.
- Ücretsiz Render uykuya geçebilir: ilk Telegram mesajı geç ulaşabilir ve Telegram webhook'u yeniden deneyebilir.

## 5. Kabul
- Telegram API webhook kayıt logu başarıyla doğrulanmalı.
- Canlı `/status`, deep link pairing, test bildirim, buton değişimleri tek tek yapılmalı.
- Token eksikken CI yalnızca **sentetik/mock** testleri tamamlar; gerçek Telegram teslimi PASS sayılmaz.

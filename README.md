# YeşilDefter

**ERP’si olmayan KOBİ’ler için yapay zekâ destekli karbon muhasebesi ve uyum platformu.**

Karbon muhasebesi 2026 itibarıyla sözleşmeye ve ihracata bağlı bir zorunluluk.
Ancak yükümlülük tedarik zincirinin ucundaki küçük işletmeye ulaştığında, o
işletmenin ne ERP’si ne de sürdürülebilirlik ekibi var; verisi kâğıt faturada
duruyor. YeşilDefter bu işletme için tasarlandı: hiçbir entegrasyon kurulmadan
belgeler yüklenir, faaliyet verisi çıkarılır, Kapsam 1-2-3 hesaplanır, emisyon
ürün birimine dağıtılır, CBAM ve TR ETS çıktıları üretilir.

Her sayı, geldiği belgenin satırına kadar izlenir. Güven skoru eşiğin
altındaysa sistem tahmin yürütmez — kullanıcıya sorar.

---

## Hızlı başlangıç

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m seed.demo        # modellenmiş örnek tesisi kurar ve zinciri çalıştırır
python run.py              # http://127.0.0.1:8000
```

Port doluysa: `PORT=8010 python run.py` (Windows'ta `set PORT=8010`).

`seed.demo` veri tabanını siler ve yeniden kurar. Sunucu AÇIKKEN çalıştırmayın:
SQLite silinen dosyayı tutmaya devam eder ve sonraki her yazma "readonly
database" hatası verir. Önce sunucuyu durdurun (Ctrl+C), sonra yeniden açın.

Dış servis anahtarı gerekmez. Dil modeli bağlı değilse belge ajanı kural
tabanlı çıkarımla çalışır ve güven skorunu buna göre düşürür.

### Yapay zekâyı bağlamak

Uygulamayı açın, **Ayarlar** sayfasına gidin, API anahtarınızı yapıştırın ve
**Bağlantıyı sına** düğmesine basın. Anahtarın biçiminden sağlayıcı kendiliğinden
tanınır:

| Anahtar başlangıcı | Sağlayıcı | Varsayılan model |
| --- | --- | --- |
| `sk-ant-` | Anthropic | claude-sonnet-4-5 |
| `sk-` / `sk-proj-` | OpenAI | gpt-4o-mini |
| `AIza` ya da `AQ.` | Google | gemini-flash-lite-latest |
| `gsk_` | Groq | llama-3.3-70b-versatile |
| `sk-or-` | OpenRouter | anthropic/claude-3.5-sonnet |
| `tgp_` | Together | Llama-3.3-70B-Instruct-Turbo |

Model adı eskirse sağlayıcı 404 ile yenisini söyler; **Ayarlar > Model**
alanına onu yazın. Ağır "düşünen" modeller sınama çağrısında zaman aşımına
uğrayabilir — o zaman daha hafif bir model (`…-lite-latest`) deneyin.
Geçici 503/429 hatalarında uygulama kendiliğinden üç kez yeniden dener.

DeepSeek ve Mistral listeden seçilir. Başka bir OpenAI uyumlu uç nokta
(yerel Ollama, LM Studio, kurum içi vLLM) için **Taban adres** alanını doldurun,
örneğin `http://localhost:11434/v1`.

Ayarlar veri tabanına yazılır ve ortam değişkenlerinin önüne geçer; anahtar
arayüzde hiçbir zaman tam gösterilmez (`sk-ant-••••••••••1234`).

### Dil modeli NEREDE çalışır

Üç yerde, hiçbirinde son sözü söylemeden:

| Görev | Ne yapar | Güvence |
| --- | --- | --- |
| Belgeden çıkarım | Faturadan miktar, birim, dönem çıkarır | Güven eşiğinin altı onay kuyruğuna düşer |
| Faktör önerisi | Kuralın tanımadığı satır için faktör önerir | **Her zaman** onay kuyruğuna düşer, asla doğrudan hesaba girmez |
| Sade dilde açıklama | Kayıtlı sayıyı ve bulguyu anlatır | Hiçbir sayıyı değiştirmez, yalnızca okur |

Dördüncü, isteğe bağlı kullanım: tedarikçiye gidecek e-postanın taslağını yazar.

Emisyon hesabı hiçbir koşulda modele bırakılmaz — çarpma işlemi
`app/core/calc.py` içindedir ve her zaman aynı sonucu verir. İstemlerin tamamı
`app/llm/prompts.py` dosyasında, okunabilir hâlde durur.

### Testler

```bash
python -m pytest -q        # 176 test
```

---

## Mimari

```
belge → faktör → faktör-yeniden → denetim → uyum → azaltım → tedarik
```

Altı ajan, tek denetim izi. Sıra `app/agents/orchestrator.py` içinde tek yerde
tanımlıdır; bir ajan hata verirse zincir durmaz, hata sonuç listesinde taşınır.

| Ajan | Dosya | Görevi |
|---|---|---|
| Belge | `agents/document_agent.py` | Fatura/irsaliye/sayaç çıktısını okur, faaliyet verisini güven skoruyla çıkarır |
| Faktör | `agents/factor_agent.py` | Doğru emisyon faktörüne bağlar, hesaplar; faktör sürümü değişince yeniden çalıştırır |
| Denetim | `agents/audit_agent.py` | Eksik dönem, aykırı değer, birim uyuşmazlığı, varsayım faktörü yakalar |
| Uyum | `agents/compliance_agent.py` | CBAM veri seti, TR ETS durumu, son tarihler |
| Azaltım | `agents/reduction_agent.py` | Tesisin kendi verisinden önlem, tCO₂e ve geri ödeme üretir |
| Tedarik | `agents/supplier_agent.py` | Kapsam 3 için tedarikçi isteği, hatırlatma ve yanıtın hesaba geçmesi |

Tedarikçi gerçek değerini bildirdiğinde, faktör ajanı bir sonraki çalışmasında
varsayım faktörü yerine o değeri kullanır ve kayıt `tier: "tedarikci"` olarak
saklanır — denetim izinde kimin bildirdiği görünür.

### Hesaplama

`app/core/calc.py` — GHG Protocol ve ISO 14064-1 çerçevesi, IPCC 2006
varsayılan faktörleri, IPCC AR5 küresel ısınma potansiyelleri.

```
58 400 m³ × 37,8 MJ/m³ ÷ 1000 = 2 207,52 GJ
2 207,52 GJ × 56,1 kgCO₂/GJ   = 123 842 kgCO₂   (+ CH₄, N₂O)
```

Sonuç tek başına saklanmaz: girdiyi, faktörü, faktörün kaynağını, sürümünü ve
uygulanan formülü birlikte taşır (`app/models.py` → `Emission.steps`).

### Dürüstlük notları

- `tier: "varsayim"` etiketli faktörler model varsayımıdır ve doğrulama öncesi
  ulusal ya da tedarikçi verisiyle değiştirilmelidir. Denetim ajanı bunu
  bulgu olarak yazar.
- Demo rakamları **modellenmiş** bir örnek tesise aittir; gerçek ölçüm değildir.
- TR ETS pilotu 50 000 tCO₂e üzerindeki tesislerde uygulanır. KOBİ genelde bu
  kapsama girmez; yükümlülük **tedarikçi** ya da **ihracatçı** olmaktan doğar.
  Uyum ajanı bunu açıkça yazar.
- Tedarikçi isteği **yalnızca SMTP tanımlıysa** gerçekten gönderilir. Tanımlı
  değilse durum `hazirlandi` olarak kalır ve ajan bunu uyarı olarak bildirir;
  gönderilmemiş bir isteği gönderilmiş gibi göstermeyiz.
- Şebeke elektriği faktörü tesisin ülkesine göre seçilir (TR / UZ). Her ikisi
  de model varsayımıdır ve resmî değerle değiştirilmelidir.

### Bilinen sınırlar

- Tek tesisli sürümdür; ikinci bir tesis kaydı oluşturulmaz.
- Taranmış (görüntü) PDF için OCR yoktur; metin çıkmazsa belge ajanı bunu
  söyler ve satır üretmez.
- Kimlik doğrulama tek katmanlıdır: `YD_PAROL` tanımlıysa tüm uygulama HTTP
  Basic ile korunur, tanımsızsa açıktır. Kullanıcı rolleri yoktur; parolayı
  bilen her şeye erişir. İnternete açık dağıtımda `YD_PAROL` zorunludur.
- Telegram botu yalnızca `TELEGRAM_ALLOWED_CHATS` listesindeki sohbetlere
  yanıt verir; liste boşsa hiç kimseye yanıt vermez.

---

## Arayüz

Beş dil: Türkçe, Oʻzbekcha, Русский, English, Türkmençe — sol alttaki
düğmelerden anında değişir. Üç tema: sistem, açık, koyu.

### Çeviri nasıl çalışır

Arayüz etiketleri `app/i18n.py` dosyasındadır. Asıl mesele çalışma anında
üretilen metinlerdir — denetim bulgusu, ajan özeti, azaltım önlemi, faktör
adı, durum sözcüğü. Bunlar veri tabanına Türkçe yazılsaydı, dili
değiştirdiğinizde sayfanın yarısı Türkçe kalırdı.

Bu yüzden üretilen her metin **kod + parametre** olarak saklanır
(`Finding.code` + `Finding.params`, `Measure.code` + `basis_params`,
`AgentResult.code` + `params`) ve ekranda kullanıcının dilinde kurulur.
Sözlük `app/messages.py` dosyasındadır. Veri tabanındaki Türkçe metin
yalnızca dışa aktarım ve denetim izi için tutulur — resmî belgeler zaten
Türkçedir.

`tests/test_dil.py` her sayfayı beş dilde gezer ve Türkçe kalıntı arar; bir
çeviri unutulursa test düşer.

| Sayfa | Yol |
|---|---|
| Pano | `/` |
| Belgeler ve yükleme | `/belgeler` |
| Denetim ve onay kuyruğu | `/denetim` |
| Ürün birimine dağıtım ve CBAM | `/urun` |
| Azaltım önlemleri | `/azaltim` |
| Tedarikçiler | `/tedarik` |
| Ajanlar ve zincir | `/ajanlar` |
| Emisyon faktörleri | `/faktorler` |
| Denetim izi | `/iz` |
| Ayarlar | `/ayarlar` |

Yüklenen belge, içerik özetiyle (SHA-256) saklanır: aynı belge ikinci kez
yüklenemez, envanter mükerrer kayıtla şişmez. Aynı faktör ve dönem için birden
çok satır oluşursa denetim ajanı bunu yüksek öncelikli bulgu olarak bildirir.

## API

| Uç nokta | Döndürdüğü |
|---|---|
| `GET /api/saglik` | sürüm, faktör sürümü, LLM durumu |
| `GET /api/ozet` | envanter, gömülü karbon, kaçınılan maliyet |
| `GET /api/rapor` | tam uyum raporu (JSON) |
| `GET /api/rapor.xlsx` | 5 sayfalı Excel raporu |
| `GET /api/rapor.pdf` | tek sayfalık özet PDF |
| `GET /api/envanter.csv` | satır satır envanter |
| `GET /api/cbam.csv` | CBAM beyanı veri seti |
| `GET /api/faktorler` | faktör tablosu ve kaynakları |

## Telegram botu

```bash
TELEGRAM_BOT_TOKEN=... python -m app.bot.telegram_bot
```

`/ozet`, `/onay`, `/rapor` komutları; faturayı doğrudan gönderince aynı ajan
zinciri çalışır ve onay bekleyen satırlar düğmeyle onaylanır.

## Yapılandırma

Üç katman, bu sırayla: **veri tabanı (Ayarlar sayfası) > ortam değişkeni >
koddaki varsayılan**. Böylece sunucuya erişimi olmayan kullanıcı da anahtarı
girebilir, ortam değişkeniyle kurulmuş dağıtım da bozulmaz.

Ayarlar sayfasından değiştirilebilenler: API anahtarı, sağlayıcı, model, taban
adres, hangi yapay zekâ görevlerinin açık olduğu, insan onayı eşiği, CBAM
sertifika fiyatı varsayımı, varsayılan dil, SMTP, Telegram jetonu ve yetkili
sohbetler, demo sıfırlama izni.

Ortam değişkenleriyle aynı değerler `.env.example` dosyasında listelidir.

Varsayılan veri tabanı SQLite’tır; `DATABASE_URL` verilince PostgreSQL
kullanılır (Railway, Render, Heroku).

## Dağıtım

```bash
docker build -t yesildefter . && docker run -p 8000:8000 yesildefter
```

Railway için `Procfile` hazırdır: `web` süreci uygulamayı, `bot` süreci
Telegram botunu çalıştırır.

Yayına almadan önce ayarlanması gereken ortam değişkenleri:

| Değişken | Değer | Neden |
| --- | --- | --- |
| `YD_PAROL` | güçlü bir parola | Tanımsızsa uygulama herkese açıktır |
| `YD_KULLANICI` | isteğe bağlı (varsayılan `jury`) | Basic kimlik kullanıcı adı |
| `DATABASE_URL` | Railway PostgreSQL eklentisi verir | SQLite yeniden dağıtımda silinir |

`/api/saglik` ve `/static/` parolanın dışındadır; sağlık yoklaması kimlik
göndermediği için bu gereklidir.

---

## Proje bilgisi

BAÜN TTO III. İnovatif Fikirler Proje Pazarı (TÜBİTAK 1503) —
“Sürdürülebilir Gelecek İçin İkiz Dönüşüm”.
Perxat Baltayev · AIFU, Yazılım Mühendisliği.

Hesaplama çerçevesi: GHG Protocol · ISO 14064-1 · IPCC 2006.

"""Dinamik metinlerin çevirisi.

Sorun: denetim bulgusu, ajan özeti, azaltım önlemi ve durum sözcükleri
çalışma anında üretilir. Bunlar veri tabanına Türkçe yazılırsa, arayüz dili
değiştiğinde yarısı çevrilmiş yarısı Türkçe bir sayfa çıkar.

Çözüm: üretilen her metin bir KOD ve PARAMETRE olarak saklanır; ekranda
kullanıcının dilinde kurulur. Veri tabanındaki Türkçe metin yalnızca dışa
aktarım ve denetim izi için tutulur — resmî belgeler zaten Türkçedir.

Kullanım:  mesaj("uz", "bulgu.onay_bekliyor", guven=55, esik=90, satir="…")
"""

from __future__ import annotations

from typing import Any, Dict

from .config import LANGS, DEFAULT_LANG

# kod -> { dil -> şablon }
MESAJ: Dict[str, Dict[str, str]] = {

    # ---------------------------------------------------------- bulgular
    "bulgu.onay_bekliyor": {
        "tr": "Güven skoru %{guven} (eşik %{esik}): '{satir}' satırı onay bekliyor.",
        "uz": "Ishonch darajasi {guven}% (chegara {esik}%): '{satir}' satri tasdiq kutmoqda.",
        "ru": "Уверенность {guven}% (порог {esik}%): строка '{satir}' ожидает подтверждения.",
        "en": "Confidence {guven}% (threshold {esik}%): row '{satir}' is awaiting approval.",
        "tk": "Ynam derejesi {guven}% (bosaga {esik}%): '{satir}' setiri tassyklama garaşýar.",
    },
    "bulgu.birim_uyusmazligi": {
        "tr": "Belgede '{okunan}' okundu, faktör '{beklenen}' bekliyor — doğrulayın.",
        "uz": "Hujjatda '{okunan}' o‘qildi, faktor '{beklenen}' kutyapti — tekshiring.",
        "ru": "В документе прочитано '{okunan}', фактор ожидает '{beklenen}' — проверьте.",
        "en": "The document says '{okunan}' but the factor expects '{beklenen}' — please verify.",
        "tk": "Resminamada '{okunan}' okaldy, faktor '{beklenen}' garaşýar — barlaň.",
    },
    "bulgu.donem_boslugu": {
        "tr": "'{faktor}' için eksik dönem: {donemler}",
        "uz": "'{faktor}' uchun yetishmayotgan davr: {donemler}",
        "ru": "Для '{faktor}' отсутствует период: {donemler}",
        "en": "Missing period for '{faktor}': {donemler}",
        "tk": "'{faktor}' üçin ýetmeýän döwür: {donemler}",
    },
    "bulgu.aykiri_deger": {
        "tr": "'{faktor}' {donem}: {deger} {birim} — medyanın {kat} katı. Belgeyi doğrulayın.",
        "uz": "'{faktor}' {donem}: {deger} {birim} — medianadan {kat} baravar yuqori. Hujjatni tekshiring.",
        "ru": "'{faktor}' {donem}: {deger} {birim} — в {kat} раза выше медианы. Проверьте документ.",
        "en": "'{faktor}' {donem}: {deger} {birim} — {kat}× the median. Verify the document.",
        "tk": "'{faktor}' {donem}: {deger} {birim} — medianadan {kat} esse ýokary. Resminamany barlaň.",
    },
    "bulgu.dusuk_deger": {
        "tr": "'{faktor}' {donem}: {deger} {birim} — medyanın altında, eksik fatura olabilir.",
        "uz": "'{faktor}' {donem}: {deger} {birim} — medianadan past, faktura yetishmasligi mumkin.",
        "ru": "'{faktor}' {donem}: {deger} {birim} — ниже медианы, возможно, не хватает счёта.",
        "en": "'{faktor}' {donem}: {deger} {birim} — below the median; an invoice may be missing.",
        "tk": "'{faktor}' {donem}: {deger} {birim} — medianadan pes, hasap ýetmeýän bolup biler.",
    },
    "bulgu.varsayim_faktor": {
        "tr": "'{faktor}' varsayım tabanlı faktör kullanıyor. Doğrulama öncesi ulusal ya da tedarikçi verisiyle değiştirilmelidir.",
        "uz": "'{faktor}' taxminiy faktordan foydalanyapti. Tekshiruvdan oldin milliy yoki yetkazib beruvchi ma'lumoti bilan almashtirilishi kerak.",
        "ru": "'{faktor}' использует допущение. До верификации его нужно заменить национальными данными или данными поставщика.",
        "en": "'{faktor}' uses an assumed factor. It must be replaced with national or supplier data before verification.",
        "tk": "'{faktor}' çaklama faktoryny ulanýar. Barlagdan öň milli ýa-da üpjün ediji maglumaty bilen çalşylmalydyr.",
    },
    "bulgu.tedarikci_faktor": {
        "tr": "'{faktor}' tedarikçinin bildirdiği gerçek değerle hesaplanıyor; varsayım faktörü kullanılmıyor.",
        "uz": "'{faktor}' yetkazib beruvchi bergan haqiqiy qiymat bilan hisoblanyapti; taxminiy faktor ishlatilmayapti.",
        "ru": "'{faktor}' считается по реальному значению поставщика; допущение не используется.",
        "en": "'{faktor}' is calculated from the supplier's reported value; no assumption is used.",
        "tk": "'{faktor}' üpjün edijiniň beren hakyky bahasy bilen hasaplanýar; çaklama ulanylmaýar.",
    },
    "bulgu.mukerrer_kayit": {
        "tr": "'{faktor}' {donem} dönemi {adet} kez kayıtlı ({satirlar}). Aynı belge birden fazla kez yüklenmiş olabilir; envanter bu kalemde şişer.",
        "uz": "'{faktor}' {donem} davri {adet} marta yozilgan ({satirlar}). Bir xil hujjat bir necha marta yuklangan bo‘lishi mumkin; inventar shu moddada shishadi.",
        "ru": "'{faktor}' за период {donem} записан {adet} раз ({satirlar}). Возможно, один документ загружен несколько раз; инвентарь по этой статье завышен.",
        "en": "'{faktor}' for {donem} is recorded {adet} times ({satirlar}). The same document may have been uploaded more than once; this line inflates the inventory.",
        "tk": "'{faktor}' {donem} döwri {adet} gezek ýazylan ({satirlar}). Bir resminama birnäçe gezek ýüklenen bolmagy mümkin; inwentar bu maddada ýokarlanýar.",
    },
    "bulgu.uretim_yok": {
        "tr": "Üretim miktarı girilmemiş; gömülü karbon (tCO₂e/ton ürün) hesaplanamaz, CBAM veri seti eksik kalır.",
        "uz": "Ishlab chiqarish miqdori kiritilmagan; mahsulotdagi karbon (tCO₂e/tonna) hisoblanmaydi, CBAM to‘plami chala qoladi.",
        "ru": "Объём производства не указан; углерод в продукте (тCO₂e/т) не рассчитывается, набор CBAM будет неполным.",
        "en": "Production volume is missing; embedded carbon (tCO₂e per tonne) cannot be calculated and the CBAM data set stays incomplete.",
        "tk": "Önümçilik möçberi girizilmedik; önümdäki uglerod (tCO₂e/tonna) hasaplanmaýar, CBAM toplumy doly bolmaýar.",
    },
    "bulgu.kapsam1_yok": {
        "tr": "Kapsam 1 (doğrudan yakıt) verisi yok. Yakıt faturası yüklenmediyse envanter eksiktir.",
        "uz": "1-qamrov (to‘g‘ridan yoqilg‘i) ma'lumoti yo‘q. Yoqilg‘i fakturasi yuklanmagan bo‘lsa inventar chala.",
        "ru": "Нет данных по области 1 (прямое топливо). Если счёт за топливо не загружен, инвентарь неполон.",
        "en": "No Scope 1 (direct fuel) data. If no fuel invoice was uploaded, the inventory is incomplete.",
        "tk": "1-gurşaw (göni ýangyç) maglumaty ýok. Ýangyç hasaby ýüklenmedik bolsa inwentar doly däl.",
    },
    "bulgu.kapsam2_yok": {
        "tr": "Kapsam 2 (satın alınan elektrik) verisi yok. Elektrik faturası yüklenmediyse envanter eksiktir.",
        "uz": "2-qamrov (sotib olingan elektr) ma'lumoti yo‘q. Elektr fakturasi yuklanmagan bo‘lsa inventar chala.",
        "ru": "Нет данных по области 2 (закупленная электроэнергия). Если счёт за электричество не загружен, инвентарь неполон.",
        "en": "No Scope 2 (purchased electricity) data. If no electricity invoice was uploaded, the inventory is incomplete.",
        "tk": "2-gurşaw (satyn alnan elektrik) maglumaty ýok. Elektrik hasaby ýüklenmedik bolsa inwentar doly däl.",
    },

    # ------------------------------------------------------- ajan özetleri
    "ajan.belge.ok": {
        "tr": "{eklenen} faaliyet satırı çıkarıldı",
        "uz": "{eklenen} ta faoliyat satri chiqarildi",
        "ru": "Извлечено строк деятельности: {eklenen}",
        "en": "{eklenen} activity rows extracted",
        "tk": "{eklenen} işjeňlik setiri çykaryldy",
    },
    "ajan.belge.oneri_eki": {
        "tr": " ({oneri} tanesi yapay zekâ önerisi)",
        "uz": " ({oneri} tasi sun'iy intellekt taklifi)",
        "ru": " (из них {oneri} — подсказка ИИ)",
        "en": " ({oneri} of them AI suggestions)",
        "tk": " ({oneri} sanysy emeli aň teklibi)",
    },
    "ajan.belge.bekleyen_eki": {
        "tr": ", {bekleyen} satır onay bekliyor",
        "uz": ", {bekleyen} satr tasdiq kutmoqda",
        "ru": ", {bekleyen} строк ожидают подтверждения",
        "en": ", {bekleyen} rows awaiting approval",
        "tk": ", {bekleyen} setir tassyklama garaşýar",
    },
    "ajan.belge.veri_yok": {
        "tr": "Belgede tanınan faaliyet verisi bulunamadı",
        "uz": "Hujjatda tanilgan faoliyat ma'lumoti topilmadi",
        "ru": "В документе не найдено распознанных данных деятельности",
        "en": "No recognised activity data found in the document",
        "tk": "Resminamada tanalan işjeňlik maglumaty tapylmady",
    },
    "ajan.belge.metin_yok": {
        "tr": "Belgeden metin çıkarılamadı (taranmış görüntü olabilir)",
        "uz": "Hujjatdan matn chiqarilmadi (skanerlangan rasm bo‘lishi mumkin)",
        "ru": "Не удалось извлечь текст (возможно, это скан)",
        "en": "No text could be extracted (it may be a scanned image)",
        "tk": "Resminamadan tekst çykarylmady (skanirlenen surat bolup biler)",
    },
    "ajan.faktor.ok": {
        "tr": "{sayi} satır hesaplandı (faktör sürümü {surum})",
        "uz": "{sayi} ta satr hisoblandi (faktor versiyasi {surum})",
        "ru": "Рассчитано строк: {sayi} (версия факторов {surum})",
        "en": "{sayi} rows calculated (factor version {surum})",
        "tk": "{sayi} setir hasaplandy (faktor wersiýasy {surum})",
    },
    "ajan.faktor.tedarikci_eki": {
        "tr": "; {sayi} faktör tedarikçi verisiyle",
        "uz": "; {sayi} ta faktor yetkazib beruvchi ma'lumoti bilan",
        "ru": "; {sayi} факторов по данным поставщика",
        "en": "; {sayi} factors from supplier data",
        "tk": "; {sayi} faktor üpjün ediji maglumaty bilen",
    },
    "ajan.faktor_yeniden.guncel": {
        "tr": "Tüm hesaplar güncel faktör sürümünde",
        "uz": "Barcha hisoblar joriy faktor versiyasida",
        "ru": "Все расчёты на актуальной версии факторов",
        "en": "All calculations are on the current factor version",
        "tk": "Ähli hasaplar häzirki faktor wersiýasynda",
    },
    "ajan.faktor_yeniden.ok": {
        "tr": "{sayi} hesap yeniden çalıştırıldı; fark {fark} tCO₂e",
        "uz": "{sayi} ta hisob qayta yuritildi; farq {fark} tCO₂e",
        "ru": "Пересчитано {sayi} записей; разница {fark} тCO₂e",
        "en": "{sayi} calculations re-run; difference {fark} tCO₂e",
        "tk": "{sayi} hasap täzeden işledildi; tapawut {fark} tCO₂e",
    },
    "ajan.denetim.ok": {
        "tr": "{bulgu} bulgu ({yuksek} yüksek öncelikli)",
        "uz": "{bulgu} ta topilma ({yuksek} tasi yuqori darajali)",
        "ru": "{bulgu} замечаний ({yuksek} высокого приоритета)",
        "en": "{bulgu} findings ({yuksek} high priority)",
        "tk": "{bulgu} tapyndy ({yuksek} ýokary derejeli)",
    },
    "ajan.denetim.temiz": {
        "tr": "Tutarsızlık bulunamadı",
        "uz": "Nomuvofiqlik topilmadi",
        "ru": "Несоответствий не найдено",
        "en": "No inconsistencies found",
        "tk": "Laýyksyzlyk tapylmady",
    },
    "ajan.uyum.ok": {
        "tr": "Envanter {toplam} tCO₂e; TR ETS {kategori}",
        "uz": "Inventar {toplam} tCO₂e; TR ETS {kategori}",
        "ru": "Инвентарь {toplam} тCO₂e; TR ETS {kategori}",
        "en": "Inventory {toplam} tCO₂e; TR ETS {kategori}",
        "tk": "Inwentar {toplam} tCO₂e; TR ETS {kategori}",
    },
    "ajan.uyum.kacinilan_eki": {
        "tr": "; kaçınılan CBAM maliyeti {tutar} €",
        "uz": "; oldini olingan CBAM xarajati {tutar} €",
        "ru": "; избежанные затраты CBAM {tutar} €",
        "en": "; avoided CBAM cost {tutar} €",
        "tk": "; öňi alnan CBAM çykdajysy {tutar} €",
    },
    "ajan.azaltim.ok": {
        "tr": "{onlem} önlem, yılda {ton} tCO₂e (envanterin %{pay}'si)",
        "uz": "{onlem} ta chora, yiliga {ton} tCO₂e (inventarning {pay}%i)",
        "ru": "{onlem} мер, {ton} тCO₂e в год ({pay}% инвентаря)",
        "en": "{onlem} measures, {ton} tCO₂e per year ({pay}% of the inventory)",
        "tk": "{onlem} çäre, ýylda {ton} tCO₂e (inwentaryň {pay}%-i)",
    },
    "ajan.azaltim.veri_yok": {
        "tr": "Önlem üretmek için yeterli faaliyet verisi yok",
        "uz": "Chora chiqarish uchun yetarli faoliyat ma'lumoti yo‘q",
        "ru": "Недостаточно данных деятельности для формирования мер",
        "en": "Not enough activity data to produce measures",
        "tk": "Çäre öndürmek üçin ýeterlik işjeňlik maglumaty ýok",
    },
    "ajan.tedarik.ok": {
        "tr": "{toplam} tedarikçi; {yanit} yanıt, {bekleyen} bekliyor (kapsama %{kapsama})",
        "uz": "{toplam} ta yetkazib beruvchi; {yanit} javob, {bekleyen} kutmoqda (qamrov {kapsama}%)",
        "ru": "{toplam} поставщиков; {yanit} ответили, {bekleyen} ожидают (покрытие {kapsama}%)",
        "en": "{toplam} suppliers; {yanit} responded, {bekleyen} pending (coverage {kapsama}%)",
        "tk": "{toplam} üpjün ediji; {yanit} jogap, {bekleyen} garaşýar (gurşaw {kapsama}%)",
    },
    "ajan.tedarik.yok": {
        "tr": "Kayıtlı tedarikçi yok",
        "uz": "Qayd etilgan yetkazib beruvchi yo‘q",
        "ru": "Нет зарегистрированных поставщиков",
        "en": "No suppliers on record",
        "tk": "Hasaba alnan üpjün ediji ýok",
    },
    "ajan.tedarik.smtp_yok": {
        "tr": "SMTP yapılandırılmadığı için istekler yalnızca hazırlandı; e-posta gönderilmedi.",
        "uz": "SMTP sozlanmagani uchun so‘rovlar faqat tayyorlandi; e-pochta yuborilmadi.",
        "ru": "SMTP не настроен, запросы только подготовлены; письма не отправлены.",
        "en": "SMTP is not configured, so requests were only prepared; no e-mail was sent.",
        "tk": "SMTP sazlanmansoň haýyşlar diňe taýýarlandy; e-poçta iberilmedi.",
    },
    "ajan.tesis_yok": {
        "tr": "Tesis bulunamadı",
        "uz": "Korxona topilmadi",
        "ru": "Предприятие не найдено",
        "en": "Facility not found",
        "tk": "Kärhana tapylmady",
    },

    # --------------------------------------------------------- önlemler
    "onlem.atik_isi": {
        "tr": "Yakma/ergitme hattında atık ısı geri kazanımı",
        "uz": "Yoqish/eritish liniyasida chiqindi issiqlikni qaytarish",
        "ru": "Рекуперация тепла на линии плавки",
        "en": "Waste-heat recovery on the melting line",
        "tk": "Eretme hatarynda galyndy ýylylygyny dikeltmek",
    },
    "onlem.ges": {
        "tr": "Çatı güneş enerjisi santrali (öz tüketim)",
        "uz": "Tom usti quyosh elektr stansiyasi (o‘z iste'moli)",
        "ru": "Крышная солнечная станция (собственное потребление)",
        "en": "Rooftop solar plant (self-consumption)",
        "tk": "Üçek gün energiýa stansiýasy (öz sarp edişi)",
    },
    "onlem.motor": {
        "tr": "Basınçlı hava kaçakları ve motor verimliliği",
        "uz": "Siqilgan havo sizishi va motor samaradorligi",
        "ru": "Утечки сжатого воздуха и КПД двигателей",
        "en": "Compressed-air leaks and motor efficiency",
        "tk": "Gysylan howa syzmalary we hereketlendiriji netijeliligi",
    },
    "onlem.yerel_tedarik": {
        "tr": "Öncül malzemede yerel/geri dönüşümlü kaynağa geçiş",
        "uz": "Xomashyoda mahalliy/qayta ishlangan manbaga o‘tish",
        "ru": "Переход на местное/вторичное сырьё",
        "en": "Switch to local or recycled input material",
        "tk": "Çig malda ýerli/gaýtadan işlenen çeşmä geçmek",
    },
    "onlem.dayanak": {
        "tr": "{taban} tabanının %{oran}'i üzerinden — model varsayımı; pilotta ölçülmüş değerle değiştirilecektir.",
        "uz": "{taban} asosining {oran}% i bo‘yicha — model taxmini; pilotda o‘lchangan qiymat bilan almashtiriladi.",
        "ru": "По {oran}% от базы {taban} — допущение модели; будет заменено измеренным значением в пилоте.",
        "en": "Based on {oran}% of the {taban} base — a model assumption, to be replaced with measured pilot data.",
        "tk": "{taban} esasynyň {oran}%-i boýunça — model çaklamasy; pilotda ölçelen baha bilen çalşylar.",
    },
    "taban.kapsam1": {
        "tr": "Kapsam 1 yakıt emisyonu", "uz": "1-qamrov yoqilg‘i emissiyasi",
        "ru": "выбросы топлива области 1", "en": "Scope 1 fuel emissions",
        "tk": "1-gurşaw ýangyç zyňyndylary",
    },
    "taban.elektrik": {
        "tr": "elektrik emisyonu", "uz": "elektr emissiyasi",
        "ru": "выбросы электроэнергии", "en": "electricity emissions",
        "tk": "elektrik zyňyndylary",
    },
    "taban.kapsam3": {
        "tr": "Kapsam 3 emisyonu", "uz": "3-qamrov emissiyasi",
        "ru": "выбросы области 3", "en": "Scope 3 emissions",
        "tk": "3-gurşaw zyňyndylary",
    },

    # ------------------------------------------------------------ TR ETS
    "ets.kapsam_ici": {
        "tr": "Tesis TR ETS pilot kapsamındadır; izleme planı ve doğrulanmış yıllık rapor yükümlülüğü doğar.",
        "uz": "Korxona TR ETS pilot qamrovida; monitoring rejasi va tekshirilgan yillik hisobot majburiyati tug‘iladi.",
        "ru": "Предприятие входит в пилот TR ETS; возникает обязанность плана мониторинга и верифицированного годового отчёта.",
        "en": "The facility is in the TR ETS pilot scope; a monitoring plan and a verified annual report become mandatory.",
        "tk": "Kärhana TR ETS pilot gurşawynda; gözegçilik meýilnamasy we barlanan ýyllyk hasabat borçlary ýüze çykýar.",
    },
    "ets.kapsam_disi": {
        "tr": "Tesis 50.000 tCO₂e eşiğinin altındadır, TR ETS pilot kapsamına girmez. Yükümlülük tedarikçi ya da ihracatçı olmaktan doğar: kapsamdaki müşteriniz ürününüzün gömülü karbonunu ister, AB alıcınız CBAM verisi ister.",
        "uz": "Korxona 50 000 tCO₂e chegarasidan past, TR ETS pilot qamroviga kirmaydi. Majburiyat yetkazib beruvchi yoki eksportchi bo‘lishdan kelib chiqadi: qamrovdagi mijozingiz mahsulotingizdagi karbonni so‘raydi, YeI xaridoringiz CBAM ma'lumotini so‘raydi.",
        "ru": "Предприятие ниже порога 50 000 тCO₂e и не входит в пилот TR ETS. Обязательство возникает как у поставщика или экспортёра: ваш клиент из периметра запросит углерод в продукте, покупатель из ЕС — данные CBAM.",
        "en": "The facility is below the 50,000 tCO₂e threshold and is outside the TR ETS pilot. The obligation arrives as a supplier or as an exporter: your in-scope customer asks for the embedded carbon of your product, your EU buyer asks for CBAM data.",
        "tk": "Kärhana 50 000 tCO₂e bosagasyndan pes, TR ETS pilot gurşawyna girmeýär. Borç üpjün ediji ýa-da eksportçy bolmakdan gelip çykýar: gurşawdaky müşderiňiz önümiňizdäki ugleroды sorar, ÝB alyjyňyz CBAM maglumatyny sorar.",
    },
    "ets.kategori.kapsam_disi": {
        "tr": "kapsam dışı", "uz": "qamrovdan tashqari", "ru": "вне периметра",
        "en": "out of scope", "tk": "gurşawdan daşynda",
    },

    # -------------------------------------------------------- son tarih
    "son_tarih.cbam_ceyrek": {
        "tr": "CBAM çeyreklik beyanı", "uz": "CBAM choraklik deklaratsiyasi",
        "ru": "Квартальная декларация CBAM", "en": "CBAM quarterly declaration",
        "tk": "CBAM çärýek beýannamasy",
    },

    # ---------------------------------------------------------- uyarılar
    "uyari.uretim_yok": {
        "tr": "Üretim miktarı yok; gömülü karbon hesaplanamadı.",
        "uz": "Ishlab chiqarish miqdori yo‘q; mahsulotdagi karbon hisoblanmadi.",
        "ru": "Нет объёма производства; углерод в продукте не рассчитан.",
        "en": "No production volume; embedded carbon was not calculated.",
        "tk": "Önümçilik möçberi ýok; önümdäki uglerod hasaplanmady.",
    },
    "uyari.ihracat_yok": {
        "tr": "AB'ye ihracat miktarı girilmemiş; CBAM maliyeti hesaplanmadı.",
        "uz": "YeIga eksport miqdori kiritilmagan; CBAM xarajati hisoblanmadi.",
        "ru": "Не указан объём экспорта в ЕС; затраты CBAM не рассчитаны.",
        "en": "EU export volume is missing; the CBAM cost was not calculated.",
        "tk": "ÝB-ä eksport möçberi girizilmedik; CBAM çykdajysy hasaplanmady.",
    },
    "uyari.veri_yukleyin": {
        "tr": "Önce fatura ve sayaç verisi yükleyin",
        "uz": "Avval faktura va hisoblagich ma'lumotini yuklang",
        "ru": "Сначала загрузите счета и показания счётчиков",
        "en": "Upload invoices and meter data first",
        "tk": "Ilki hasap we hasaplaýjy maglumatyny ýükläň",
    },
}

# tek sözcüklük durum ve etiketler
ETIKET: Dict[str, Dict[str, str]] = {
    # faaliyet satırı durumu
    "onayli": {"tr": "Onaylı", "uz": "Tasdiqlangan", "ru": "Подтверждено",
               "en": "Approved", "tk": "Tassyklanan"},
    "onay_bekliyor": {"tr": "Onay bekliyor", "uz": "Tasdiq kutmoqda",
                      "ru": "Ожидает", "en": "Awaiting approval",
                      "tk": "Garaşýar"},
    "reddedildi": {"tr": "Reddedildi", "uz": "Rad etilgan", "ru": "Отклонено",
                   "en": "Rejected", "tk": "Ret edildi"},
    # tedarikçi durumu
    "bekliyor": {"tr": "Bekliyor", "uz": "Kutmoqda", "ru": "Ожидает",
                 "en": "Pending", "tk": "Garaşýar"},
    "hazirlandi": {"tr": "Hazırlandı", "uz": "Tayyorlandi", "ru": "Подготовлено",
                   "en": "Prepared", "tk": "Taýýarlandy"},
    "gonderildi": {"tr": "Gönderildi", "uz": "Yuborildi", "ru": "Отправлено",
                   "en": "Sent", "tk": "Iberildi"},
    "hatirlatildi": {"tr": "Hatırlatıldı", "uz": "Eslatildi", "ru": "Напомнили",
                     "en": "Reminded", "tk": "Ýatladyldy"},
    "yanitladi": {"tr": "Yanıtladı", "uz": "Javob berdi", "ru": "Ответил",
                  "en": "Responded", "tk": "Jogap berdi"},
    "yanitsiz": {"tr": "Yanıtsız", "uz": "Javobsiz", "ru": "Без ответа",
                 "en": "No response", "tk": "Jogapsyz"},
    "istek_gonderildi": {"tr": "İstek gönderildi", "uz": "So‘rov yuborildi",
                         "ru": "Запрос отправлен", "en": "Request sent",
                         "tk": "Haýyş iberildi"},
    # belge durumu
    "islendi": {"tr": "İşlendi", "uz": "Qayta ishlandi", "ru": "Обработано",
                "en": "Processed", "tk": "Işlenen"},
    "veri_yok": {"tr": "Veri yok", "uz": "Ma'lumot yo‘q", "ru": "Нет данных",
                 "en": "No data", "tk": "Maglumat ýok"},
    # çıkarım yöntemi
    "kural": {"tr": "Kural", "uz": "Qoida", "ru": "Правила", "en": "Rules",
              "tk": "Düzgün"},
    "llm": {"tr": "Yapay zekâ", "uz": "Sun'iy intellekt", "ru": "ИИ",
            "en": "AI", "tk": "Emeli aň"},
    "llm+oneri": {"tr": "Yapay zekâ + öneri", "uz": "SI + taklif",
                  "ru": "ИИ + подсказка", "en": "AI + suggestion",
                  "tk": "Emeli aň + teklip"},
    "kural+oneri": {"tr": "Kural + öneri", "uz": "Qoida + taklif",
                    "ru": "Правила + подсказка", "en": "Rules + suggestion",
                    "tk": "Düzgün + teklip"},
    # faktör düzeyi
    "ipcc": {"tr": "IPCC", "uz": "IPCC", "ru": "IPCC", "en": "IPCC", "tk": "IPCC"},
    "ulusal": {"tr": "Ulusal", "uz": "Milliy", "ru": "Национальный",
               "en": "National", "tk": "Milli"},
    "varsayim": {"tr": "Varsayım", "uz": "Taxmin", "ru": "Допущение",
                 "en": "Assumption", "tk": "Çaklama"},
    "tedarikci": {"tr": "Tedarikçi", "uz": "Yetkazib beruvchi",
                  "ru": "Поставщик", "en": "Supplier", "tk": "Üpjün ediji"},
    # bulgu kodlarının kısa adı
    "kod.onay_bekliyor": {"tr": "Onay bekliyor", "uz": "Tasdiq kutmoqda",
                          "ru": "Ожидает подтверждения",
                          "en": "Awaiting approval", "tk": "Tassyklama garaşýar"},
    "kod.birim_uyusmazligi": {"tr": "Birim uyuşmazlığı", "uz": "Birlik nomuvofiqligi",
                              "ru": "Несовпадение единиц", "en": "Unit mismatch",
                              "tk": "Birlik laýyksyzlygy"},
    "kod.donem_boslugu": {"tr": "Dönem boşluğu", "uz": "Davr bo‘shlig‘i",
                          "ru": "Пропуск периода", "en": "Period gap",
                          "tk": "Döwür boşlugy"},
    "kod.aykiri_deger": {"tr": "Aykırı değer", "uz": "Chetga chiqqan qiymat",
                         "ru": "Выброс значения", "en": "Outlier",
                         "tk": "Çykgynsyz baha"},
    "kod.dusuk_deger": {"tr": "Düşük değer", "uz": "Past qiymat",
                        "ru": "Заниженное значение", "en": "Low value",
                        "tk": "Pes baha"},
    "kod.varsayim_faktor": {"tr": "Varsayım faktörü", "uz": "Taxminiy faktor",
                            "ru": "Фактор-допущение", "en": "Assumed factor",
                            "tk": "Çaklama faktory"},
    "kod.tedarikci_faktor": {"tr": "Tedarikçi faktörü", "uz": "Yetkazib beruvchi faktori",
                             "ru": "Фактор поставщика", "en": "Supplier factor",
                             "tk": "Üpjün ediji faktory"},
    "kod.mukerrer_kayit": {"tr": "Mükerrer kayıt", "uz": "Takroriy yozuv",
                           "ru": "Дубликат записи", "en": "Duplicate record",
                           "tk": "Gaýtalanan ýazgy"},
    "kod.uretim_yok": {"tr": "Üretim verisi yok", "uz": "Ishlab chiqarish ma'lumoti yo‘q",
                       "ru": "Нет данных производства", "en": "No production data",
                       "tk": "Önümçilik maglumaty ýok"},
    "kod.kapsam1_yok": {"tr": "Kapsam 1 yok", "uz": "1-qamrov yo‘q",
                        "ru": "Нет области 1", "en": "No Scope 1",
                        "tk": "1-gurşaw ýok"},
    "kod.kapsam2_yok": {"tr": "Kapsam 2 yok", "uz": "2-qamrov yo‘q",
                        "ru": "Нет области 2", "en": "No Scope 2",
                        "tk": "2-gurşaw ýok"},

    # bulgu önceliği
    "yuksek": {"tr": "Yüksek", "uz": "Yuqori", "ru": "Высокий", "en": "High",
               "tk": "Ýokary"},
    "uyari": {"tr": "Uyarı", "uz": "Ogohlantirish", "ru": "Предупреждение",
              "en": "Warning", "tk": "Duýduryş"},
    "bilgi": {"tr": "Bilgi", "uz": "Ma'lumot", "ru": "Информация", "en": "Info",
              "tk": "Maglumat"},
    # ajan adları
    "belge": {"tr": "Belge ajanı", "uz": "Hujjat agenti", "ru": "Агент документов",
              "en": "Document agent", "tk": "Resminama agenti"},
    "faktor": {"tr": "Faktör ajanı", "uz": "Faktor agenti", "ru": "Агент факторов",
               "en": "Factor agent", "tk": "Faktor agenti"},
    "faktor_yeniden": {"tr": "Faktör güncelleme ajanı",
                       "uz": "Faktor yangilash agenti",
                       "ru": "Агент обновления факторов",
                       "en": "Factor update agent",
                       "tk": "Faktor täzeleýji agent"},
    "denetim": {"tr": "Denetim ajanı", "uz": "Tekshiruv agenti",
                "ru": "Агент проверки", "en": "Assurance agent",
                "tk": "Barlag agenti"},
    "uyum": {"tr": "Uyum ajanı", "uz": "Muvofiqlik agenti",
             "ru": "Агент соответствия", "en": "Compliance agent",
             "tk": "Laýyklyk agenti"},
    "azaltim": {"tr": "Azaltım ajanı", "uz": "Kamaytirish agenti",
                "ru": "Агент снижения", "en": "Reduction agent",
                "tk": "Azaltmak agenti"},
    "tedarik": {"tr": "Tedarik zinciri ajanı", "uz": "Yetkazib beruvchi agenti",
                "ru": "Агент цепочки поставок", "en": "Supply chain agent",
                "tk": "Üpjünçilik zynjyry agenti"},
}


def _dil(lang: str | None) -> str:
    return lang if lang in LANGS else DEFAULT_LANG


def mesaj(lang: str | None, code: str, **params: Any) -> str:
    """Kodu kullanıcının dilinde metne çevirir.

    Bilinmeyen kod ya da eksik parametre sayfayı bozmaz: kod aynen döner.
    """
    kalip = MESAJ.get(code)
    if not kalip:
        return code
    metin = kalip.get(_dil(lang)) or kalip.get("tr") or code
    try:
        return metin.format(**params)
    except (KeyError, IndexError, ValueError):
        return metin


def etiket(lang: str | None, anahtar: str) -> str:
    """Durum/etiket sözcüğünü çevirir; bilinmiyorsa aynen döner."""
    e = ETIKET.get(str(anahtar))
    if not e:
        return str(anahtar)
    return e.get(_dil(lang)) or e.get("tr") or str(anahtar)


def ceviri_kontrol() -> list[str]:
    """Eksik çeviri varsa listeler — testlerde kullanılır."""
    eksik = []
    for ad, sozluk in (("MESAJ", MESAJ), ("ETIKET", ETIKET)):
        for code, diller in sozluk.items():
            for d in LANGS:
                if d not in diller or not diller[d].strip():
                    eksik.append(f"{ad}.{code}.{d}")
    return eksik


# ------------------------------------------------------------- faktör adları
FAKTOR_ADI: Dict[str, Dict[str, str]] = {
    "dogalgaz": {"tr": "Doğal gaz", "uz": "Tabiiy gaz", "ru": "Природный газ",
                 "en": "Natural gas", "tk": "Tebigy gaz"},
    "motorin": {"tr": "Motorin (dizel)", "uz": "Dizel yoqilg‘isi",
                "ru": "Дизельное топливо", "en": "Diesel", "tk": "Dizel ýangyjy"},
    "benzin": {"tr": "Benzin", "uz": "Benzin", "ru": "Бензин",
               "en": "Petrol", "tk": "Benzin"},
    "lpg": {"tr": "LPG", "uz": "Suyultirilgan gaz (LPG)",
            "ru": "Сжиженный газ (LPG)", "en": "LPG", "tk": "Suwuklandyrylan gaz"},
    "fuel_oil": {"tr": "Fuel-oil", "uz": "Mazut (fuel-oil)", "ru": "Мазут",
                 "en": "Fuel oil", "tk": "Mazut"},
    "komur": {"tr": "Taş kömürü", "uz": "Toshko‘mir", "ru": "Каменный уголь",
              "en": "Hard coal", "tk": "Daş kömür"},
    "elektrik_tr": {"tr": "Elektrik — Türkiye şebekesi",
                    "uz": "Elektr — Turkiya tarmog‘i",
                    "ru": "Электроэнергия — сеть Турции",
                    "en": "Electricity — Türkiye grid",
                    "tk": "Elektrik — Türkiýe ulgamy"},
    "elektrik_uz": {"tr": "Elektrik — Özbekistan şebekesi",
                    "uz": "Elektr — O‘zbekiston tarmog‘i",
                    "ru": "Электроэнергия — сеть Узбекистана",
                    "en": "Electricity — Uzbekistan grid",
                    "tk": "Elektrik — Özbegistan ulgamy"},
    "buhar_satin": {"tr": "Satın alınan buhar", "uz": "Sotib olingan bug‘",
                    "ru": "Закупленный пар", "en": "Purchased steam",
                    "tk": "Satyn alnan bug"},
    "hurda_celik": {"tr": "Hurda çelik (satın alınan)",
                    "uz": "Temir-tersak po‘lat (sotib olingan)",
                    "ru": "Стальной лом (закупленный)",
                    "en": "Scrap steel (purchased)",
                    "tk": "Polat galyndysy (satyn alnan)"},
    "birincil_alum": {"tr": "Birincil alüminyum", "uz": "Birlamchi alyuminiy",
                      "ru": "Первичный алюминий", "en": "Primary aluminium",
                      "tk": "Birinji alýuminiý"},
    "hurda_alum": {"tr": "Hurda alüminyum", "uz": "Alyuminiy chiqindisi",
                   "ru": "Алюминиевый лом", "en": "Scrap aluminium",
                   "tk": "Alýuminiý galyndysy"},
    "cimento": {"tr": "Çimento (satın alınan)", "uz": "Sement (sotib olingan)",
                "ru": "Цемент (закупленный)", "en": "Cement (purchased)",
                "tk": "Sement (satyn alnan)"},
    "karayolu_tasima": {"tr": "Karayolu taşıma", "uz": "Avtomobil tashuvi",
                        "ru": "Автомобильные перевозки",
                        "en": "Road freight", "tk": "Awtoulag daşamasy"},
    "atik_duzenli": {"tr": "Düzenli depolama atığı", "uz": "Poligon chiqindisi",
                     "ru": "Отходы на полигоне", "en": "Landfilled waste",
                     "tk": "Polygon galyndysy"},
}

# faktör kaynağı açıklamaları
KAYNAK_ADI: Dict[str, Dict[str, str]] = {
    "ipcc": {"tr": "IPCC 2006 varsayılan değeri",
             "uz": "IPCC 2006 standart qiymati",
             "ru": "Значение по умолчанию IPCC 2006",
             "en": "IPCC 2006 default value",
             "tk": "IPCC 2006 adaty bahasy"},
    "ulusal": {"tr": "Ulusal yayımlanmış değer", "uz": "Milliy e'lon qilingan qiymat",
               "ru": "Опубликованное национальное значение",
               "en": "Published national value", "tk": "Milli neşir edilen baha"},
    "varsayim": {"tr": "Model varsayımı — doğrulama öncesi değiştirilmelidir",
                 "uz": "Model taxmini — tekshiruvdan oldin almashtirilishi kerak",
                 "ru": "Допущение модели — заменить до верификации",
                 "en": "Model assumption — replace before verification",
                 "tk": "Model çaklamasy — barlagdan öň çalşylmaly"},
    "tedarikci": {"tr": "Tedarikçinin bildirdiği değer",
                  "uz": "Yetkazib beruvchi bergan qiymat",
                  "ru": "Значение, сообщённое поставщиком",
                  "en": "Value reported by the supplier",
                  "tk": "Üpjün edijiniň beren bahasy"},
}


def faktor_adi(lang: str | None, key: str, varsayilan: str = "") -> str:
    """Faktörün kullanıcının dilindeki adı."""
    e = FAKTOR_ADI.get(key)
    if not e:
        return varsayilan or key
    return e.get(_dil(lang)) or e.get("tr") or varsayilan or key


def kaynak_adi(lang: str | None, tier: str, varsayilan: str = "") -> str:
    e = KAYNAK_ADI.get(str(tier))
    if not e:
        return varsayilan or str(tier)
    return e.get(_dil(lang)) or e.get("tr") or varsayilan or str(tier)

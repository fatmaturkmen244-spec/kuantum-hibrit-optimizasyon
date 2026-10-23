# Quantum Route Lab — Hibrit Kuantum Optimizasyon Motoru

Microsoft Azure OpenAI, Microsoft QDK ve Azure Quantum entegrasyonuna hazır; doğal dille anlatılan rota problemlerini klasik ve kuantum yöntemlerle karşılaştıran eğitim amaçlı hibrit optimizasyon laboratuvarı.

## Canlı bağlantılar

- **Herkese açık web demosu:** https://fatmaturkmen244-spec.github.io/kuantum-hibrit-optimizasyon/
- **Sunum:** [Quantum_Route_Lab_Sunum_v2.pptx](Quantum_Route_Lab_Sunum_v2.pptx)
- **2 dakikalık proje videosu:** https://youtu.be/JZYghIdtH5U

Web demosu tarayıcı içinde kesin, klasik hızlı ve kuantum-esinli olasılık modelini çalıştırır. Microsoft Q# ve Azure Quantum özellikleri, Python/QDK tabanlı tam uygulamada çalışır; arayüz bu seviyeleri birbirinden açıkça ayırır.

## Demo neler yapıyor?

- 3–10 istasyon için kapalı rota oluşturur.
- Simulated Annealing ve durum-vektörü tabanlı QAOA-benzeri simülatörü karşılaştırır.
- 9 istasyona kadar kesin çözümü kalite ölçütü olarak hesaplar.
- FastAPI üzerinden JSON API ve Streamlit üzerinden profesyonel deney arayüzü sunar.
- Azure OpenAI yapılandırılmışsa sonuçları doğal dille açıklar; yapılandırılmamışsa tamamen yerel çalışır.
- İsteğe bağlı QDK modu, küçük problemleri gerçek Q# kuantum devresine çevirip yerel QDK simülatöründe veya bir Azure Quantum hedefinde çalıştırır.
- Kullanıcı “İstanbul, Ankara ve İzmir için en kısa turu kuantumla karşılaştır” gibi bir cümle yazarak deneyi başlatabilir.
- Azure OpenAI bağlıysa doğal dil girdisini yapılandırır; bağlı değilse desteklenen şehirler için yerel ayrıştırıcı çalışır.
- Mesafe, süre ve kesin referansa göre kalite farkını aynı ekranda ölçer.
- Kazanan rotayı çizer; qubit, ölçüm, olasılık, kapı ailesi ve devre parmak izini gösterir.
- Her deney için kuantum avantajının gözlenip gözlenmediğini dürüstçe yorumlar.
- Sonuç ekranı kuantum seviyesini üç basamakta gösterir: kuantum modeli, Microsoft Q# devresi ve Azure Quantum işi.

> **Bilimsel sınır:** `quantum_simulator`, geçerli turların indirgenmiş durum uzayında maliyet fazı ve difüzyon karıştırıcısı kullanan eğitim amaçlı bir simülatördür. Azure Quantum donanım işi veya tam kapı düzeyi QAOA değildir.

`qdk_qaoa` ise Q# ile kapı düzeyi devre kurar ve Microsoft QDK üzerinde çalışır. Demo en fazla 5 istasyonla sınırlıdır. Yerel simülatörde çalışması gerçek kuantum donanım avantajı anlamına gelmez; Azure hedefi ayrıca yapılandırılmalıdır.

Arayüzdeki **Kuantum kanıtı** bölümü backend, qubit, ölçüm sayısı, QDK sürümü, kullanılan kapı ailesi, ölçüm dağılımı ve devre parmak izini gösterir. Azure Quantum kullanıldığında ayrıca doğrulanabilir Azure iş kimliği görüntülenir.

## Diğer rota uygulamalarından farkı

Bu proje bir navigasyon uygulaması değildir. Kullanıcının doğal dille anlattığı kombinatoryal problemi kesin klasik arama, klasik sezgisel arama, QAOA-benzeri statevector ve Q# kapı devresiyle çözen bir **karşılaştırma laboratuvarıdır**. Amaç “kuantum” etiketini göstermek değil; kuantum devresinin çözüm kalitesine, ölçüm dağılımına ve çalışma süresine etkisini denetlenebilir verilerle görünür kılmaktır.

## Kurulum

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Gerçek QDK devre modu için ek bağımlılıkları kurun:

```powershell
python -m pip install -e ".[dev,quantum]"
```

Arayüzü başlatın:

```powershell
streamlit run streamlit_app.py
```

API'yi başlatın:

```powershell
uvicorn hybrid_quantum.api:app --reload
```

API belgeleri `http://127.0.0.1:8000/docs` adresindedir.

## Örnek API isteği

```json
{
  "cities": [
    {"name": "A", "x": 0, "y": 0},
    {"name": "B", "x": 2, "y": 0},
    {"name": "C", "x": 2, "y": 2},
    {"name": "D", "x": 0, "y": 2}
  ],
  "seed": 42,
  "annealing_iterations": 4000,
  "quantum_layers": 3
}
```

## Azure OpenAI (isteğe bağlı)

`.env.example` dosyasını `.env` olarak kopyalayıp değerleri doldurun. Anahtarları Git'e eklemeyin. Uygulama bu dosyayı başlangıçta otomatik yükler.

## Doğal dille kullanım örneği

Arayüzde **Yazarak çöz** sekmesini açın ve örneğin şu cümleyi yazın:

> İstanbul'dan başlayıp Ankara, İzmir, Antalya ve Bursa'yı ziyaret eden en kısa turu bul. Klasik yöntemlerle kuantum yöntemini karşılaştır.

Web demosu, desteklenen 14 şehrin WGS84 şehir merkezi GPS referans noktalarını kullanır; koordinatlar ve OpenStreetMap pinleri sonuç ekranında gösterilir. Büyük şehirlerde tek bir evrensel merkez olmadığı için bu noktalar kapı/adres değil, doğrulanabilir şehir merkezi referanslarıdır. Varsayılan modda mesafe hesabı Haversine (kuş uçuşu) kilometreleridir. Azure Maps proxy'si bağlandığında ise aynı demo gerçek sürüş mesafesi ve tahmini sürüş süresi matrisini kullanır; arayüz hangi kaynağın kullanıldığını açıkça yazar.

## Gerçek yol verisi · Azure Maps proxy

GitHub Pages statik olduğu için Azure Maps anahtarı kesinlikle `docs/` altına veya tarayıcı JavaScript'ine konmaz. Güvenli akış şöyledir:

```text
GitHub Pages → FastAPI proxy → Azure Maps Search / Route Matrix
```

Yeni API uçları:

- `POST /maps/geocode`: adresi WGS84 konumuna çözer; rota için uygun nokta varsa onu tercih eder.
- `POST /maps/route-matrix`: 2–10 konum için yönlü gerçek yol mesafesi (metre) ve süre (saniye) matrisi döndürür.
- `POST /maps/optimize`: önce yolu hesaplar, ardından kesin, klasik, kuantum-simülatör ve istenirse Q# çözücülerinin **tamamını aynı matriste** çalıştırır.

Yerelde veya Azure App Service / Container Apps üzerinde API'yi dağıtırken sunucunun güvenli ortam değişkenlerine şunları ekleyin:

```text
AZURE_MAPS_SUBSCRIPTION_KEY=...
AZURE_MAPS_ENDPOINT=https://atlas.microsoft.com
```

Ardından yalnızca proxy URL'sini `docs/runtime-config.js` içindeki `apiBaseUrl` alanına yazın. Bu URL gizli değildir; anahtar boşta kalır ve yalnızca sunucudadır. URL boş bırakılırsa demo bozulmaz, mevcut GPS + kuş uçuşu yedeği çalışır. Public API için varsayılan CORS listesi yalnız GitHub Pages ve yerel geliştirme adreslerini kapsar; dağıtımda gerekirse `CORS_ALLOW_ORIGINS` ile açıkça genişletin.

Eski yerel arayüzdeki `/api/config` yardımcı endpoint'i varsayılan olarak kapalıdır; yalnız `ENABLE_LOCAL_CONFIG=true` ile ve `localhost` üzerinde çalışır. Public dağıtımda anahtarlar her zaman ortam değişkeni, Key Vault veya yönetilen kimlik üzerinden verilmelidir.

Route Matrix v2025-01-01'in GeoJSON koordinat düzeni `[longitude, latitude]` olduğundan, istemci bunu doğrular ve matrisi yanıt listesinin sırasına değil `originIndex` / `destinationIndex` alanlarına göre kurar. Varsayılan trafik modu `historical`dır; deneylerin tekrar üretilebilir kalmasını sağlar. [Azure Maps Route Matrix belgeleri](https://learn.microsoft.com/en-us/rest/api/maps/route/post-route-matrix?view=rest-maps-2026-01-01) ve [Geocoding belgeleri](https://learn.microsoft.com/en-us/rest/api/maps/search/get-geocoding?view=rest-maps-2026-01-01) ayrıntılı şemayı açıklar.

## Test

```powershell
pytest
```

## Sonraki adımlar

1. Doğal dilde problem tanımını yapılandırılmış modele çevirme
2. Azure Maps'ten gelen rota geometrisiyle haritada gerçek yol çizgisini gösterme
3. Deney geçmişini kalıcı olarak saklama ve dışa aktarma
4. QAOA parametre optimizasyonunu ve sağlayıcıya özel transpilation'ı geliştirme

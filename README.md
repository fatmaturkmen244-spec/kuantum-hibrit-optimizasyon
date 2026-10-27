# Quantum Route Lab — Hibrit Kuantum Optimizasyon Motoru

Microsoft Azure OpenAI, Microsoft QDK ve Azure Quantum entegrasyonuna hazır; doğal dille anlatılan rota problemlerini klasik ve kuantum yöntemlerle karşılaştıran eğitim amaçlı hibrit optimizasyon laboratuvarı.

## Canlı bağlantılar

- **Canlı laboratuvar:** https://fatmaturkmen244-spec.github.io/kuantum-hibrit-optimizasyon/
- **Sunum:** [Quantum_Route_Lab_Sunum_v2.pptx](Quantum_Route_Lab_Sunum_v2.pptx)

Web laboratuvarı tarayıcı içinde kesin, klasik hızlı ve kuantum-esinli olasılık modelini çalıştırır. Microsoft Q# ve Azure Quantum özellikleri, Python/QDK tabanlı tam uygulamada çalışır; arayüz bu seviyeleri birbirinden açıkça ayırır.

## Laboratuvar neler yapıyor?

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
- V2 ile, rota dışında Max-Cut ağ bölme problemi de klasik, kesin ve kuantum-esinli yöntemlerle görselleştirilebilir.

> **Bilimsel sınır:** `quantum_simulator`, geçerli turların indirgenmiş durum uzayında maliyet fazı ve difüzyon karıştırıcısı kullanan eğitim amaçlı bir simülatördür. Azure Quantum donanım işi veya tam kapı düzeyi QAOA değildir.

`qdk_qaoa` ise Q# ile kapı düzeyi devre kurar ve Microsoft QDK üzerinde çalışır. Bu Q# yolu en fazla 5 istasyonla sınırlıdır. Yerel simülatörde çalışması gerçek kuantum donanım avantajı anlamına gelmez; Azure hedefi ayrıca yapılandırılmalıdır.

Arayüzdeki **Kuantum kanıtı** bölümü backend, qubit, ölçüm sayısı, QDK sürümü, kullanılan kapı ailesi, ölçüm dağılımı ve devre parmak izini gösterir. Azure Quantum kullanıldığında ayrıca doğrulanabilir Azure iş kimliği görüntülenir.

## Diğer rota uygulamalarından farkı

Bu proje bir navigasyon uygulaması değildir. Kullanıcının doğal dille anlattığı kombinatoryal problemi kesin klasik arama, klasik sezgisel arama, QAOA-benzeri statevector ve Q# kapı devresiyle çözen bir **karşılaştırma laboratuvarıdır**. Amaç “kuantum” etiketini göstermek değil; kuantum devresinin çözüm kalitesine, ölçüm dağılımına ve çalışma süresine etkisini denetlenebilir verilerle görünür kılmaktır.

## V2 · Max-Cut ağ bölme

Max-Cut, ağırlıklı bir ilişki ağını iki kümeye ayırırken iki küme arasına taşınan bağlantı ağırlığını en üst düzeye çıkarır. Laboratuvardaki ilk senaryo, ödeme, kargo, iade, teslimat ve kampanya işlerinin görünür bağımlılıklarını kullanır. Kullanıcı düğüm adlarını normal Türkçe ile yazar; sayfa seçilen düğümler için kesin arama, klasik bit-flip tavlama ve kuantum-esinli olasılık modelini aynı anda çalıştırır.

Bu tarayıcı akışı gerçek bir yerel optimizasyon hesabıdır; “kuantum olasılık modeli” donanım veya Q# sonucu olarak temsil edilmez. Python API'deki Max-Cut çözüm ucu, serbest metni yalnızca açık `Düğümler:` ve `Kenarlar:` şemasıyla kabul eder ve tüm grafiği doğruladıktan sonra çözer. Bu sınır, doğal dil yorumunun görünmez veya hatalı bir kuantum modeline dönüşmesini engeller.

API tarafında aynı problemi açık biçimde göndermek için `POST /maxcut/solve` kullanılır:

```json
{
  "problem": "Düğümler: Ödeme, Kargo, İade. Kenarlar: Ödeme-Kargo:3, Ödeme-İade:9, Kargo-İade:4.",
  "seed": 42,
  "annealing_iterations": 2000,
  "quantum_layers": 2
}
```

Yanıt, doğrulanmış grafiği, `E = -kesim_ağırlığı` QUBO matrisini, üç yöntemin kümelerini ve kesilen kenarları birlikte döndürür.

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

## Konumla kullanım

Canlı laboratuvarda önce **Konum ekle** alanına il, ilçe, açık adres veya mağaza adı yazın. İl ve ilçe araması sayfada yerel olarak çalışır; örneğin `Kadıköy, İstanbul` sonucunu seçip durağa ekleyebilirsiniz. En az üç, en fazla sekiz durağı seçin ve **Rotayı çöz ve karşılaştır** düğmesine basın.

İsterseniz aşağıdaki gibi bir cümleyle de başlayabilirsiniz:

> İstanbul'dan başlayıp Ankara, İzmir, Antalya ve Bursa'yı ziyaret eden en kısa turu bul. Klasik yöntemlerle kuantum yöntemini karşılaştır.

`docs/data/turkiye-il-ilce-konumlari.json`, Türkiye’nin **81 ili ve 973 ilçesi** için WGS84 idari alan referans koordinatları içerir. Veri, [Turkey Administrative Divisions](https://github.com/open-admin-data/turkey-administrative-divisions) veri kümesinden türetilmiştir ve [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) atfıyla kullanılır. Bu noktalar bir ev kapısı, mağaza girişi veya doğrulanmış belediye merkezi değildir; idari alanlar için katalog referanslarıdır. Varsayılan modda mesafe hesabı Haversine (kuş uçuşu) kilometreleridir.

Açık adres ve mağaza/işletme araması için Azure Maps proxy'si bağlanmalıdır. Kullanıcıya en fazla beş aday gösterilir ve doğru aday kullanıcı tarafından seçilir; belirsiz bir isim otomatik rotaya eklenmez. Proxy bağlandığında rota matrisi gerçek sürüş mesafesi ve tahmini süreyi kullanır; arayüz hangi veri modunda olduğunu açıkça yazar.

Paylaşım için yerel HTML dosyasını değil, yalnızca şu canlı adresi kullanın: `https://fatmaturkmen244-spec.github.io/kuantum-hibrit-optimizasyon/`. Yerel dosya çift tıklanırsa sayfa bu genel adrese yönlenir; böylece bilgisayardaki klasör yolu paylaşılmaz.

## Gerçek yol verisi · Azure Maps proxy

GitHub Pages statik olduğu için Azure Maps anahtarı kesinlikle `docs/` altına veya tarayıcı JavaScript'ine konmaz. Güvenli akış şöyledir:

```text
GitHub Pages → FastAPI proxy → Azure Maps Search / Route Matrix
```

Yeni API uçları:

- `POST /maps/geocode`: adresi WGS84 konumuna çözer; rota için uygun nokta varsa onu tercih eder.
- `POST /maps/places`: Türkiye kapsamındaki adres geocoding ile mağaza/işletme POI aramasını birleştirir. Yalnızca en fazla beş normalleştirilmiş aday döner; Azure Maps anahtarı veya sağlayıcı kimliği tarayıcıya gönderilmez.
- `POST /maps/route-matrix`: 2–10 konum için yönlü gerçek yol mesafesi (metre) ve süre (saniye) matrisi döndürür.
- `POST /maps/optimize`: önce yolu hesaplar, ardından kesin, klasik, kuantum-simülatör ve istenirse Q# çözücülerinin **tamamını aynı matriste** çalıştırır.

Yerelde veya Azure App Service / Container Apps üzerinde API'yi dağıtırken sunucunun güvenli ortam değişkenlerine şunları ekleyin:

```text
AZURE_MAPS_SUBSCRIPTION_KEY=...
AZURE_MAPS_ENDPOINT=https://atlas.microsoft.com
```

Ardından yalnızca proxy URL'sini `docs/runtime-config.js` içindeki `apiBaseUrl` alanına yazın. Bu URL gizli değildir; anahtar boşta kalır ve yalnızca sunucudadır. URL boş bırakılırsa laboratuvar bozulmaz: 81 il/973 ilçe kataloğu ve kuş uçuşu yedeği çalışır, fakat açık adres/mağaza araması açıkça devre dışı görünür. Public API için varsayılan CORS listesi yalnız GitHub Pages ve yerel geliştirme adreslerini kapsar; dağıtımda gerekirse `CORS_ALLOW_ORIGINS` ile açıkça genişletin.

> **Canlıya alma notu:** `/maps/places` tek bir kullanıcı aramasında adres ve POI için iki Azure isteği çalıştırır. Uygulama içindeki `MAPS_RATE_LIMIT_PER_MINUTE` yalnızca tek işlemli bir korumadır; herkese açık dağıtımda API Management, Front Door/WAF veya eşdeğeri bir katmanda IP/istemci başına kota ve istek sınırı zorunludur. Ham adres metinlerini uygulama günlüklerine yazmayın.

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

# Quantum Route Lab — Hibrit Kuantum Optimizasyon Motoru

Microsoft Azure OpenAI, Microsoft QDK ve Azure Quantum entegrasyonuna hazır; doğal dille anlatılan rota problemlerini klasik ve kuantum yöntemlerle karşılaştıran eğitim amaçlı hibrit optimizasyon laboratuvarı.

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

Demo şehir kataloğu yaklaşık coğrafi koordinatlar kullanır; sonuçlar gerçek yol veya trafik mesafesi değildir.

## Test

```powershell
pytest
```

## Sonraki adımlar

1. Doğal dilde problem tanımını yapılandırılmış modele çevirme
2. Harita koordinatları ve gerçek yol mesafesi matrisi
3. Deney geçmişini kalıcı olarak saklama ve dışa aktarma
4. QAOA parametre optimizasyonunu ve sağlayıcıya özel transpilation'ı geliştirme

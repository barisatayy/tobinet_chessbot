# TobiNet Chess AI

TobiNet, PyTorch derin öğrenme mimarisi üzerine inşa edilmiş özel satranç motorlarına ve modern, mobil uyumlu bir web arayüzüne sahip bir satranç yapay zekasıdır.

---

## Özellikler

- **Yapay Zeka Motorları:**
  - **Tobi Light:** Hızlı değerlendirme ve sezgisel hamle seçimi.
  - **Tobi Mid:** Derin arama ve pozisyon analizi ile güçlendirilmiş ResNet mimarisi.
- **Modern Web Arayüzü:**
  - Hem masaüstü hem de mobil cihazlar için optimize edilmiş responsive tasarım.
  - **Hamle İnceleme:** Oynanan maç esnasında veya maç bittiğinde yön tuşları ya da navigasyon butonlarıyla hamleleri ileri-geri sarıp anlık analiz yapabilme.
- **Oyun Modları & Süre:**
  - 1, 3, 5, 10, 15 dakika veya sınırsız süre seçenekleri.

---

## Kurulum

### 1. Depoyu Klonlayın
```bash
git clone https://github.com/barisatayy/tobinet_chessbot.git
cd tobinet_chessbot
```

> **Not:** Ağırlık dosyaları Git LFS ile yönetilmektedir. Model dosyalarını çekmek için `git lfs pull` komutunu çalıştırabilirsiniz.

### 2. Bağımlılıkları Yükleyin
```bash
pip install -r requirements.txt
```

---

## Çalıştırma

Sunucuyu başlatmak için:
```bash
python server.py
```
*(Windows kullanıcıları doğrudan `TobiNet_Baslat.bat` dosyasına çift tıklayarak da başlatabilir.)*

Sunucu açıldıktan sonra tarayıcınızdan şu adrese gidin:
```
http://localhost:5000
```

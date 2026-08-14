import os
import sys
import subprocess
import webbrowser
import time

def run_cmd(args, shell=True):
    print(f"Executing: {' '.join(args) if isinstance(args, list) else args}")
    result = subprocess.run(args, shell=shell, capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        print(f"Error executing command. Code: {result.returncode}")
        print(f"Stderr: {result.stderr}")
        return False, result.stdout + "\n" + result.stderr
    return True, result.stdout

def setup_and_run():
    print("====================================================")
    print("   HIBRIT KUANTUM OPTIMIZASYON MOTORU KURULUMU      ")
    print("====================================================")
    
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(workspace_dir)
    
    # 1. Check Python version
    print(f"[1/4] Python versiyonu kontrol ediliyor: {sys.version}")
    
    # 2. Virtual environment setup
    venv_dir = os.path.join(workspace_dir, "venv")
    pip_path = os.path.join(venv_dir, "Scripts", "pip.exe") if os.name == "nt" else os.path.join(venv_dir, "bin", "pip")
    python_path = os.path.join(venv_dir, "Scripts", "python.exe") if os.name == "nt" else os.path.join(venv_dir, "bin", "python")
    
    if not os.path.exists(venv_dir):
        print("[2/4] Sanal ortam (venv) olusturuluyor... Lutfen bekleyin.")
        success, out = run_cmd([sys.executable, "-m", "venv", "venv"])
        if not success:
            print("[ERROR] Sanal ortam olusturulamadi. Islem durduruluyor.")
            return
        print("[OK] Sanal ortam basariyla olusturuldu.")
    else:
        print("[2/4] Sanal ortam zaten mevcut, atlanıyor.")
        
    # 3. Install requirements
    print("[3/4] Bagimliliklar yukleniyor/guncelleniyor... Bu islem birkac dakika surebilir.")
    req_file = os.path.join(workspace_dir, "requirements.txt")
    if os.path.exists(req_file):
        # Upgrade pip first
        run_cmd([python_path, "-m", "pip", "install", "--upgrade", "pip"])
        
        # Install packages
        success, out = run_cmd([python_path, "-m", "pip", "install", "-r", "requirements.txt"])
        if not success:
            print("[WARNING] Bazi bagimliliklar yuklenemedi (Qiskit derleme hatasi Windows'ta C++ araclarinin eksikliginden kaynaklanabilir).")
            print("Fakat endiseniz olmasin! Gelistirdigimiz motor, Qiskit olmasa bile saf NumPy tabanli")
            print("klasik simulasyon modunu (fall-back) kullanarak uctan uca calismaya devam edecektir.")
        else:
            print("[OK] Tum bagimliliklar basariyla yuklendi.")
    else:
        print("[ERROR] requirements.txt dosyasi bulunamadi!")
        return

    # 4. Start Server
    print("[4/4] FastAPI Sunucusu baslatiliyor...")
    print("Tarayiciniz otomatik olarak http://127.0.0.1:8000 adresinde acilacaktir.")
    
    # We will open the browser after a short delay
    def open_browser():
        time.sleep(2.0)
        webbrowser.open("http://127.0.0.1:8000")
        
    import threading
    threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        # Start uvicorn
        subprocess.run([python_path, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"])
    except KeyboardInterrupt:
        print("\nSunucu kapatildi. Iyi calismalar!")

if __name__ == "__main__":
    setup_and_run()

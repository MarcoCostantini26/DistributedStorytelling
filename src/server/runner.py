import subprocess
import time
import sys
import os

# Percorso del file main.py del server
SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "main.py")

def run_server():
    print("--- [WATCHDOG] Avvio del Server Storytelling ---")
    while True:
        try:
            # Avvia il server come sottoprocesso usando lo stesso interprete Python
            process = subprocess.Popen([sys.executable, SERVER_SCRIPT])
            
            # Aspetta che il processo finisca (o crasci)
            process.wait()
            
            exit_code = process.returncode
            print(f"--- [WATCHDOG] Il server è terminato con codice {exit_code} ---")
            
            if exit_code == 0:
                print("--- [WATCHDOG] Chiusura volontaria. Arresto watchdog.")
                break
            else:
                print("--- [WATCHDOG] Rilevato CRASH. Riavvio automatico tra 3 secondi... ---")
                time.sleep(3)
                
        except KeyboardInterrupt:
            print("\n--- [WATCHDOG] Interrotto dall'utente. Uscita. ---")
            if 'process' in locals():
                process.terminate()
            break
        except Exception as e:
            print(f"--- [WATCHDOG] Errore critico: {e}")
            break

if __name__ == "__main__":
    run_server()
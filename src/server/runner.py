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
            # Avvia il server come sottoprocesso
            # sys.executable assicura che usiamo lo stesso interprete python corrente
            process = subprocess.Popen([sys.executable, SERVER_SCRIPT])
            
            # Aspetta che il processo finisca (o crasci)
            process.wait()
            
            # Se siamo qui, il server è terminato/crashato
            exit_code = process.returncode
            print(f"--- [WATCHDOG] ATTENZIONE: Il server è terminato con codice {exit_code} ---")
            
            if exit_code == 0:
                # Se il codice è 0, significa che è stato chiuso volontariamente (es. manutenzione)
                print("--- [WATCHDOG] Chiusura volontaria. Arresto watchdog.")
                break
            else:
                # Se il codice è diverso da 0, è un crash. Riavvio!
                print("--- [WATCHDOG] Rilevato CRASH. Riavvio automatico tra 3 secondi... ---")
                time.sleep(3)
                
        except KeyboardInterrupt:
            print("\n--- [WATCHDOG] Interrotto dall'utente. Uscita. ---")
            if 'process' in locals():
                process.terminate()
            break
        except Exception as e:
            print(f"--- [WATCHDOG] Errore critico nel runner: {e}")
            break

if __name__ == "__main__":
    run_server()
import subprocess
import time
import sys
import os

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "__main__.py")

def run_server():
    server_args = sys.argv[1:]
    mode_str = " ".join(server_args) if server_args else "MASTER"
    
    print(f"--- [WATCHDOG] Avvio del Server Storytelling ({mode_str}) ---")
    
    while True:
        try:
            cmd = [sys.executable, SERVER_SCRIPT] + server_args
            process = subprocess.Popen(cmd)
            process.wait()
            
            exit_code = process.returncode
            print(f"--- [WATCHDOG] Il server è terminato con codice {exit_code} ---")
            
            if exit_code == 0:
                print("--- [WATCHDOG] Chiusura volontaria.")
                break
            else:
                print("--- [WATCHDOG] Rilevato CRASH. Riavvio tra 3 secondi... ---")
                time.sleep(3)
                
        except KeyboardInterrupt:
            print("\n--- [WATCHDOG] Interrotto dall'utente. ---")
            if 'process' in locals(): process.terminate()
            break
        except Exception as e:
            print(f"--- [WATCHDOG] Errore critico: {e}")
            break

if __name__ == "__main__":
    run_server()
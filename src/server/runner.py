import subprocess
import time
import sys
import os

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "main.py")

def run_server():
    """
    Watchdog process: monitors the server lifecycle.
    - Restarts automatically on crash (exit code != 0).
    - Stops on clean exit (exit code 0).
    """
    print("--- [WATCHDOG] Avvio del Server Storytelling ---")
    
    while True:
        try:
            # Launch server using the same Python interpreter (virtualenv safe)
            process = subprocess.Popen([sys.executable, SERVER_SCRIPT])
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
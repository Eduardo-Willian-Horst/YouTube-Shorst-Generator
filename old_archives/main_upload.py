import schedule
import time
import subprocess
import os
from datetime import datetime

def upload():
    print(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Upload starting...")
    try:
        resultado = subprocess.run(
            ["python", "upload_video.py"],
            capture_output=True,
            text=True
        )
        
        if resultado.stdout:
            print("output:", resultado.stdout)
        if resultado.stderr:
            print("errors:", resultado.stderr)
            
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Upload complete:", resultado.returncode)
    except Exception as e:
        print(f"Error: {e}")

def main():
    print("YouTube Upload")
    print("The upload will be executed daily at 18:00")
    print("Press Ctrl+C to exit\n")
    
    upload()
    
    schedule.every().day.at("18:00").do(upload)
    
    while True:
        schedule.run_pending()
        time.sleep(60) 

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")

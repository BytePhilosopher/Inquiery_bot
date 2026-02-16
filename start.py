import multiprocessing
import subprocess

def run_bot():
    subprocess.run(["python", "app/bot.py"])

def run_dashboard():
    subprocess.run(["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"])

if __name__ == "__main__":
    p1 = multiprocessing.Process(target=run_bot)
    p2 = multiprocessing.Process(target=run_dashboard)

    p1.start()
    p2.start()

    p1.join()
    p2.join()

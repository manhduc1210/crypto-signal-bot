from .settings import Settings

def main():
    s = Settings.load()
    print("="*60)
    print("Crypto Signal Bot — Step 2 (Ingestion & Candle Builder)")
    print("-"*60)
    print(s.summary())
    print("Next: run ingestion with `python -m app.ingest` to see TF closes in console.")
    print("="*60)

if __name__ == '__main__':
    main()

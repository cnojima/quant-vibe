import os
import schwabdev
import time
from dotenv import load_dotenv
from datetime import datetime


load_dotenv()

def main():
    """Initialize SchwabDev client and streamer."""

    print("="*70)
    print("SCHWABDEV STREAMER INITIALIZATION")
    print(f"Time: {datetime.now()}")
    print("="*70)

    # Initialize SchwabDev client
    print("\nInitializing SchwabDev client...")

    client = schwabdev.Client(
      os.getenv("SCHWAB_API_KEY"),
      os.getenv("SCHWAB_API_SECRET"),
      os.getenv("SCHWAB_CALLBACK_URL"),
    )
    streamer = schwabdev.Stream(client)

    def my_handler(message):
        print("demo_handler: " + message)
    streamer.start(my_handler)
    print("✅ SchwabDev streamer started")


    streamer.send(streamer.level_one_futures("/ES", "0,1,2,3,4,5,6"))
    print("✅ Subscribed to /ES level one futures data")

    time.sleep(300)
    streamer.stop()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✅ Streaming stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

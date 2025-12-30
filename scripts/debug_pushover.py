#!/usr/bin/env python
"""Debug Pushover configuration and test notifications."""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

# Load .env
load_dotenv()

print("="*70)
print("PUSHOVER DEBUG TOOL")
print("="*70)

# Check environment variables
api_token = os.getenv("PUSHOVER_API_TOKEN")
user_key = os.getenv("PUSHOVER_USER_KEY")
device = os.getenv("PUSHOVER_DEVICE")
enabled = os.getenv("PUSHOVER_ENABLED", "true")

print("\n1. Environment Variables:")
print(f"   PUSHOVER_API_TOKEN: {'✅ Set' if api_token else '❌ MISSING'}")
if api_token:
    print(f"      Length: {len(api_token)} chars")
    print(f"      Preview: {api_token[:8]}..." if len(api_token) > 8 else f"      Value: {api_token}")

print(f"   PUSHOVER_USER_KEY: {'✅ Set' if user_key else '❌ MISSING'}")
if user_key:
    print(f"      Length: {len(user_key)} chars")
    print(f"      Preview: {user_key[:8]}...")

print(f"   PUSHOVER_DEVICE: {device if device else 'Not set (will use all devices)'}")
print(f"   PUSHOVER_ENABLED: {enabled}")

if not api_token or not user_key:
    print("\n❌ ERROR: Missing required credentials!")
    print("\nPlease set in your .env file:")
    print("   PUSHOVER_API_TOKEN=your_application_api_token")
    print("   PUSHOVER_USER_KEY=your_user_key")
    print("\nGet your credentials from:")
    print("   1. User Key: https://pushover.net (shown on dashboard)")
    print("   2. API Token: https://pushover.net/apps/build (create an application)")
    sys.exit(1)

# Try importing the notifier
print("\n2. Importing PushoverNotifier...")
try:
    from quant_vibe.notifications import PushoverNotifier, NotificationPriority
    print("   ✅ Import successful")
except Exception as e:
    print(f"   ❌ Import failed: {e}")
    sys.exit(1)

# Initialize notifier
print("\n3. Initializing notifier...")
try:
    notifier = PushoverNotifier(
        api_token=api_token,
        user_key=user_key,
        device=device,
        enabled=enabled.lower() == "true"
    )
    print(f"   ✅ Notifier initialized")
    print(f"      Enabled: {notifier.enabled}")
except Exception as e:
    print(f"   ❌ Initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Validate credentials
print("\n4. Validating credentials with Pushover API...")
try:
    is_valid = notifier.validate()
    if is_valid:
        print("   ✅ Credentials are VALID!")
    else:
        print("   ❌ Credentials validation FAILED")
        print("   Check that your API token and user key are correct")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Validation error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Send test notification
print("\n5. Sending test notification...")
try:
    success = notifier.send(
        title="QuantVibe Test",
        message="If you see this, your Pushover integration is working!",
        priority=NotificationPriority.NORMAL
    )

    if success:
        print("   ✅ Test notification SENT successfully!")
        print("\n📱 Check your device for the notification")
    else:
        print("   ❌ Failed to send notification")
        print("   Check the error messages above")
except Exception as e:
    print(f"   ❌ Send error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*70)
print("✅ PUSHOVER DEBUG COMPLETE")
print("="*70)

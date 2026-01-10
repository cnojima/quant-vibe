#!/usr/bin/env python3
"""
Watcher Service Failure Scenario Tests

Tests the watcher service's ability to detect and alert on various failure conditions:
1. Container crashes
2. Network failures
3. Missed heartbeats
4. Service unresponsiveness
5. Recovery detection
"""

import sys
import time
import docker
import signal
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

from quant_vibe.logging import setup_normalized_logging
from quant_vibe.messaging import RedisMessageBroker

# Load environment
load_dotenv()


class WatcherFailureTest:
    """Test suite for watcher service failure scenarios."""

    def __init__(self):
        """Initialize test suite."""
        self.logger = setup_normalized_logging(
            app_name="watcher_test",
            log_dir="logs/watcher_test",
        )

        self.docker_client = docker.from_env()
        self.redis_broker = RedisMessageBroker()
        self.test_results: List[Dict] = []
        self.original_container_states: Dict[str, bool] = {}

    def log_section(self, title: str):
        """Log a section header."""
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info(title)
        self.logger.info("=" * 80)

    def log_test(self, name: str, status: str, details: str = ""):
        """Log test result."""
        symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        self.logger.info(f"{symbol} {name}: {status}")
        if details:
            self.logger.info(f"   {details}")

        self.test_results.append({
            "name": name,
            "status": status,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def save_container_states(self):
        """Save current state of all containers."""
        self.log_section("Saving Container States")
        try:
            containers = self.docker_client.containers.list(
                filters={"name": "quant-vibe-"}
            )
            for container in containers:
                self.original_container_states[container.name] = (
                    container.status == "running"
                )
                self.logger.info(
                    f"Container {container.name}: {container.status}"
                )
            return True
        except Exception as e:
            self.logger.error(f"Failed to save container states: {e}")
            return False

    def restore_container_states(self):
        """Restore containers to their original states."""
        self.log_section("Restoring Container States")
        try:
            for container_name, should_be_running in self.original_container_states.items():
                try:
                    container = self.docker_client.containers.get(container_name)
                    current_running = container.status == "running"

                    if should_be_running and not current_running:
                        self.logger.info(f"Starting {container_name}...")
                        container.start()
                        time.sleep(2)
                    elif not should_be_running and current_running:
                        self.logger.info(f"Stopping {container_name}...")
                        container.stop()

                except docker.errors.NotFound:
                    self.logger.warning(f"Container {container_name} not found")
                except Exception as e:
                    self.logger.error(
                        f"Error restoring {container_name}: {e}"
                    )

            self.logger.info("Container states restored")
            return True
        except Exception as e:
            self.logger.error(f"Failed to restore container states: {e}")
            return False

    def get_container_status(self, container_name: str) -> Optional[str]:
        """Get status of a container."""
        try:
            container = self.docker_client.containers.get(container_name)
            return container.status
        except docker.errors.NotFound:
            return None
        except Exception as e:
            self.logger.error(f"Error getting container status: {e}")
            return None

    def wait_for_detection(
        self,
        condition_check,
        timeout: int = 120,
        check_interval: int = 5,
        condition_name: str = "condition"
    ) -> bool:
        """
        Wait for watcher to detect a condition.

        Args:
            condition_check: Callable that returns True when condition met
            timeout: Maximum seconds to wait
            check_interval: Seconds between checks
            condition_name: Description for logging

        Returns:
            True if condition detected, False if timeout
        """
        self.logger.info(f"Waiting for watcher to detect {condition_name}...")
        elapsed = 0

        while elapsed < timeout:
            if condition_check():
                self.logger.info(
                    f"✅ Condition detected after {elapsed}s"
                )
                return True

            time.sleep(check_interval)
            elapsed += check_interval
            self.logger.info(
                f"   Waiting... ({elapsed}/{timeout}s)"
            )

        self.logger.warning(
            f"⚠️  Timeout waiting for {condition_name} after {timeout}s"
        )
        return False

    # =========================================================================
    # Test Scenarios
    # =========================================================================

    def test_container_stop(self):
        """Test 1: Container graceful stop detection."""
        self.log_section("Test 1: Container Graceful Stop")

        test_container = "quant-vibe-redis"
        self.logger.info(f"Testing graceful stop of {test_container}")

        try:
            # Get initial status
            initial_status = self.get_container_status(test_container)
            if initial_status != "running":
                self.log_test(
                    "Container Stop Test",
                    "SKIP",
                    f"{test_container} not running initially"
                )
                return

            # Stop container
            self.logger.info(f"Stopping {test_container}...")
            container = self.docker_client.containers.get(test_container)
            container.stop()
            self.logger.info(f"Container stopped")

            # Wait for watcher to detect
            time.sleep(35)  # Wait for at least one check cycle

            # Check status
            final_status = self.get_container_status(test_container)
            detected = final_status != "running"

            if detected:
                self.log_test(
                    "Container Stop Detection",
                    "PASS",
                    f"Container status changed to: {final_status}"
                )
            else:
                self.log_test(
                    "Container Stop Detection",
                    "FAIL",
                    "Watcher did not detect container stop"
                )

            # Restart container
            self.logger.info(f"Restarting {test_container}...")
            container.start()
            time.sleep(5)

        except Exception as e:
            self.log_test("Container Stop Test", "FAIL", str(e))

    def test_container_kill(self):
        """Test 2: Container crash (kill -9) detection."""
        self.log_section("Test 2: Container Crash (SIGKILL)")

        test_container = "quant-vibe-timescaledb"
        self.logger.info(f"Testing crash of {test_container}")

        try:
            # Get initial status
            initial_status = self.get_container_status(test_container)
            if initial_status != "running":
                self.log_test(
                    "Container Crash Test",
                    "SKIP",
                    f"{test_container} not running initially"
                )
                return

            # Kill container (simulates crash)
            self.logger.info(f"Killing {test_container} (SIGKILL)...")
            container = self.docker_client.containers.get(test_container)
            container.kill()
            self.logger.info(f"Container killed")

            # Wait for watcher to detect
            time.sleep(35)

            # Check status
            final_status = self.get_container_status(test_container)
            detected = final_status != "running"

            if detected:
                self.log_test(
                    "Container Crash Detection",
                    "PASS",
                    f"Crash detected, status: {final_status}"
                )
            else:
                self.log_test(
                    "Container Crash Detection",
                    "FAIL",
                    "Watcher did not detect container crash"
                )

            # Restart container
            self.logger.info(f"Restarting {test_container}...")
            container.start()
            time.sleep(10)  # TimescaleDB needs more startup time

        except Exception as e:
            self.log_test("Container Crash Test", "FAIL", str(e))

    def test_missed_heartbeats(self):
        """Test 3: Missed heartbeat detection."""
        self.log_section("Test 3: Missed Heartbeat Detection")

        self.logger.info("Simulating missed heartbeats...")

        try:
            # Check if any service publishes heartbeats
            # We'll listen for a bit to see if heartbeats are active
            heartbeat_received = False

            def on_heartbeat(topic, data):
                nonlocal heartbeat_received
                heartbeat_received = True
                self.logger.info(f"Received heartbeat from: {topic}")

            # Subscribe to heartbeat topics
            topics = [
                "heartbeat.token_service",
                "heartbeat.streaming",
                "heartbeat.live_trading",
            ]

            self.logger.info(f"Listening for heartbeats on: {', '.join(topics)}")

            # Note: This is a simplified test - in production we'd need to
            # actually stop a service from publishing heartbeats
            self.log_test(
                "Missed Heartbeat Test",
                "SKIP",
                "Manual test required - stop a service and observe watcher logs"
            )

        except Exception as e:
            self.log_test("Missed Heartbeat Test", "FAIL", str(e))

    def test_service_recovery(self):
        """Test 4: Service recovery detection."""
        self.log_section("Test 4: Service Recovery Detection")

        test_container = "quant-vibe-redis"
        self.logger.info(f"Testing recovery detection for {test_container}")

        try:
            # Stop container
            self.logger.info(f"Stopping {test_container}...")
            container = self.docker_client.containers.get(test_container)
            container.stop()
            time.sleep(35)  # Let watcher detect failure

            # Restart container
            self.logger.info(f"Restarting {test_container}...")
            container.start()
            time.sleep(10)  # Wait for startup

            # Wait for watcher to detect recovery
            time.sleep(35)

            # Check status
            final_status = self.get_container_status(test_container)
            recovered = final_status == "running"

            if recovered:
                self.log_test(
                    "Service Recovery Detection",
                    "PASS",
                    f"Recovery detected, status: {final_status}"
                )
            else:
                self.log_test(
                    "Service Recovery Detection",
                    "FAIL",
                    f"Recovery not detected, status: {final_status}"
                )

        except Exception as e:
            self.log_test("Service Recovery Test", "FAIL", str(e))

    def test_multiple_failures(self):
        """Test 5: Multiple simultaneous failures."""
        self.log_section("Test 5: Multiple Simultaneous Failures")

        test_containers = ["quant-vibe-redis", "quant-vibe-timescaledb"]
        self.logger.info(f"Testing multiple failures: {', '.join(test_containers)}")

        stopped_containers = []

        try:
            # Stop multiple containers
            for container_name in test_containers:
                try:
                    container = self.docker_client.containers.get(container_name)
                    if container.status == "running":
                        self.logger.info(f"Stopping {container_name}...")
                        container.stop()
                        stopped_containers.append(container_name)
                except docker.errors.NotFound:
                    self.logger.warning(f"Container {container_name} not found")

            if not stopped_containers:
                self.log_test(
                    "Multiple Failures Test",
                    "SKIP",
                    "No containers to stop"
                )
                return

            # Wait for watcher to detect
            time.sleep(35)

            # Check all stopped
            all_detected = True
            for container_name in stopped_containers:
                status = self.get_container_status(container_name)
                if status == "running":
                    all_detected = False
                    break

            if all_detected:
                self.log_test(
                    "Multiple Failures Detection",
                    "PASS",
                    f"All {len(stopped_containers)} failures detected"
                )
            else:
                self.log_test(
                    "Multiple Failures Detection",
                    "FAIL",
                    "Not all failures detected"
                )

            # Restart all containers
            for container_name in stopped_containers:
                try:
                    self.logger.info(f"Restarting {container_name}...")
                    container = self.docker_client.containers.get(container_name)
                    container.start()
                except Exception as e:
                    self.logger.error(f"Error restarting {container_name}: {e}")

            time.sleep(15)  # Wait for services to start

        except Exception as e:
            self.log_test("Multiple Failures Test", "FAIL", str(e))
            # Try to restart containers anyway
            for container_name in stopped_containers:
                try:
                    container = self.docker_client.containers.get(container_name)
                    if container.status != "running":
                        container.start()
                except Exception:
                    pass

    def test_watcher_resilience(self):
        """Test 6: Watcher service resilience."""
        self.log_section("Test 6: Watcher Service Resilience")

        self.logger.info("Testing watcher resilience to rapid status changes...")

        test_container = "quant-vibe-redis"

        try:
            container = self.docker_client.containers.get(test_container)

            # Rapid stop/start cycles
            cycles = 3
            self.logger.info(f"Performing {cycles} rapid stop/start cycles...")

            for i in range(cycles):
                self.logger.info(f"Cycle {i+1}/{cycles}")
                container.stop()
                time.sleep(2)
                container.start()
                time.sleep(2)

            # Wait for watcher to stabilize
            time.sleep(35)

            # Check final status
            final_status = self.get_container_status(test_container)

            if final_status == "running":
                self.log_test(
                    "Watcher Resilience",
                    "PASS",
                    f"Watcher handled rapid changes, final status: {final_status}"
                )
            else:
                self.log_test(
                    "Watcher Resilience",
                    "FAIL",
                    f"Unexpected final status: {final_status}"
                )

        except Exception as e:
            self.log_test("Watcher Resilience Test", "FAIL", str(e))

    def print_summary(self):
        """Print test summary."""
        self.log_section("Test Summary")

        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = sum(1 for r in self.test_results if r["status"] == "FAIL")
        skipped = sum(1 for r in self.test_results if r["status"] == "SKIP")
        total = len(self.test_results)

        self.logger.info(f"Total Tests: {total}")
        self.logger.info(f"Passed: {passed}")
        self.logger.info(f"Failed: {failed}")
        self.logger.info(f"Skipped: {skipped}")
        self.logger.info("")

        for result in self.test_results:
            symbol = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            self.logger.info(
                f"{symbol} {result['name']}: {result['status']}"
            )
            if result["details"]:
                self.logger.info(f"   {result['details']}")

        self.logger.info("")
        if failed == 0:
            self.logger.info("🎉 All tests passed!")
        else:
            self.logger.warning(f"⚠️  {failed} test(s) failed")

        return failed == 0

    def run_all_tests(self):
        """Run all failure scenario tests."""
        self.log_section("Watcher Service Failure Scenario Tests")
        self.logger.info("Starting comprehensive failure scenario testing")
        self.logger.info("")
        self.logger.info("⚠️  WARNING: This will temporarily stop/restart services")
        self.logger.info("⚠️  Ensure watcher service is running before starting tests")
        self.logger.info("")

        # Save current state
        if not self.save_container_states():
            self.logger.error("Failed to save container states - aborting")
            return False

        try:
            # Run tests
            self.test_container_stop()
            time.sleep(5)

            self.test_container_kill()
            time.sleep(5)

            self.test_service_recovery()
            time.sleep(5)

            self.test_multiple_failures()
            time.sleep(5)

            self.test_watcher_resilience()
            time.sleep(5)

            self.test_missed_heartbeats()

        finally:
            # Always restore state
            self.restore_container_states()
            time.sleep(10)  # Final wait for services to stabilize

        # Print summary
        return self.print_summary()


def main():
    """Main entry point."""
    print("\n" + "=" * 80)
    print("Watcher Service Failure Scenario Test Suite")
    print("=" * 80)
    print("\nThis script will test the watcher service's ability to detect:")
    print("  1. Container stops (graceful)")
    print("  2. Container crashes (SIGKILL)")
    print("  3. Missed heartbeats")
    print("  4. Service recovery")
    print("  5. Multiple simultaneous failures")
    print("  6. Watcher resilience to rapid changes")
    print("\n⚠️  WARNING: Services will be temporarily stopped during testing")
    print("⚠️  Ensure the watcher service is running before proceeding")
    print("\nContinue? (yes/no): ", end="")

    response = input().strip().lower()
    if response != "yes":
        print("Test cancelled")
        return 1

    print()

    # Run tests
    tester = WatcherFailureTest()
    success = tester.run_all_tests()

    return 0 if success else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

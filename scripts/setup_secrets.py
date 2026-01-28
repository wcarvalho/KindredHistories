#!/usr/bin/env python3
"""
Setup Google Cloud Secret Manager secrets from .env file.

This script securely reads secrets from your .env file and creates them
in Google Cloud Secret Manager without exposing them in terminal history.

Usage:
    python setup_secrets.py
    # or
    uv run python setup_secrets.py
"""

import os
import subprocess
import sys
from pathlib import Path

# Try to import dotenv
try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv not installed")
    print("Install with: pip install python-dotenv")
    print("Or: uv pip install python-dotenv")
    sys.exit(1)


def run_command(cmd, input_data=None, check=True):
    """Run a shell command with optional stdin input."""
    try:
        result = subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=True,
            check=check
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout, e.stderr


def secret_exists(secret_name):
    """Check if a secret already exists in Secret Manager."""
    cmd = ["gcloud", "secrets", "describe", secret_name]
    returncode, _, _ = run_command(cmd, check=False)
    return returncode == 0


def create_secret(secret_name, secret_value):
    """Create a secret in Google Cloud Secret Manager."""
    if secret_exists(secret_name):
        print(f"  ℹ️  Secret '{secret_name}' already exists")
        response = input(f"     Do you want to add a new version? (y/N): ").strip().lower()

        if response == 'y':
            # Add new version to existing secret
            cmd = ["gcloud", "secrets", "versions", "add", secret_name, "--data-file=-"]
            returncode, stdout, stderr = run_command(cmd, input_data=secret_value)

            if returncode == 0:
                print(f"  ✅ Added new version to '{secret_name}'")
                return True
            else:
                print(f"  ❌ Failed to add version to '{secret_name}'")
                print(f"     Error: {stderr}")
                return False
        else:
            print(f"  ⏭️  Skipping '{secret_name}'")
            return True
    else:
        # Create new secret
        cmd = ["gcloud", "secrets", "create", secret_name, "--data-file=-"]
        returncode, stdout, stderr = run_command(cmd, input_data=secret_value)

        if returncode == 0:
            print(f"  ✅ Created secret '{secret_name}'")
            return True
        else:
            print(f"  ❌ Failed to create secret '{secret_name}'")
            print(f"     Error: {stderr}")
            return False


def main():
    print("🔐 Google Cloud Secret Manager Setup")
    print("=" * 50)

    # Check if .env file exists
    env_path = Path(".env")
    if not env_path.exists():
        print("\n❌ ERROR: .env file not found in current directory")
        print("   Make sure you're running this script from the repository root")
        sys.exit(1)

    # Load environment variables
    load_dotenv(env_path)

    # Check if gcloud is installed
    returncode, _, _ = run_command(["gcloud", "--version"], check=False)
    if returncode != 0:
        print("\n❌ ERROR: gcloud CLI not found")
        print("   Install from: https://cloud.google.com/sdk/docs/install")
        sys.exit(1)

    # Get current project
    returncode, stdout, stderr = run_command(["gcloud", "config", "get-value", "project"], check=False)
    if returncode != 0 or not stdout.strip():
        print("\n❌ ERROR: No GCP project configured")
        print("   Set project with: gcloud config set project YOUR_PROJECT_ID")
        sys.exit(1)

    project_id = stdout.strip()
    print(f"\n📍 Current GCP Project: {project_id}")

    # Confirm before proceeding
    print("\nThis will create the following secrets:")
    print("  • gemini-api-key (from GEMINI_API_KEY)")
    print("  • google-cse-api-key (from GOOGLE_CSE_API_KEY)")
    print("  • google-cse-id (from GOOGLE_CSE_ID)")

    response = input("\nProceed? (y/N): ").strip().lower()
    if response != 'y':
        print("Cancelled.")
        sys.exit(0)

    print("\n🔄 Creating secrets...")

    # Define secrets to create
    secrets_map = {
        "gemini-api-key": "GEMINI_API_KEY",
        "google-cse-api-key": "GOOGLE_CSE_API_KEY",
        "google-cse-id": "GOOGLE_CSE_ID",
    }

    success_count = 0
    failed_secrets = []

    for secret_name, env_var in secrets_map.items():
        secret_value = os.getenv(env_var)

        if not secret_value:
            print(f"  ⚠️  Warning: {env_var} not found in .env file")
            failed_secrets.append(secret_name)
            continue

        if create_secret(secret_name, secret_value):
            success_count += 1
        else:
            failed_secrets.append(secret_name)

    # Summary
    print("\n" + "=" * 50)
    print(f"✨ Summary: {success_count}/{len(secrets_map)} secrets configured")

    if failed_secrets:
        print(f"\n⚠️  Failed or skipped secrets: {', '.join(failed_secrets)}")

    print("\n📝 Next steps:")
    print("1. Verify secrets were created:")
    print("   gcloud secrets list")
    print("\n2. Deploy your Cloud Run service with these secrets:")
    print("   gcloud run deploy kindred-histories-backend \\")
    print("     --source . \\")
    print("     --region us-central1 \\")
    print("     --set-secrets 'GEMINI_API_KEY=gemini-api-key:latest,GOOGLE_CSE_API_KEY=google-cse-api-key:latest,GOOGLE_CSE_ID=google-cse-id:latest'")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()

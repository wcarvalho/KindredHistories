#!/usr/bin/env python3
"""
Script to clear all historical figures from the Firestore database.

Usage:
    uv run python clear_database.py
"""
import os

import firebase_admin
from firebase_admin import credentials, firestore


def clear_all_figures():
  """Delete non-initial documents in the historical_figures collection.

  Preserves figures where initial=True (pre-populated figures).
  Only deletes figures where initial=False or initial field is missing.
  """
  # Initialize Firebase
  cred_path = os.path.expanduser("~/firebase-keys/kindred-histories-firebase-key.json")

  if os.path.exists(cred_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
    print(f"Using credentials from {cred_path}")
  elif os.path.exists("service-account-key.json"):
    cred_path = "service-account-key.json"
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
    print(f"Using credentials from {cred_path}")
  else:
    print("Error: No Firebase credentials found!")
    return

  # Initialize Firebase app if not already initialized
  if not firebase_admin._apps:
    try:
      cred = credentials.Certificate(cred_path)
      firebase_admin.initialize_app(cred)
      print("Firebase initialized successfully")
    except Exception as e:
      print(f"Failed to initialize Firebase: {e}")
      return

  # Get Firestore client
  try:
    db = firestore.client()
    print("Connected to Firestore database")
  except Exception as e:
    print(f"Firestore client creation failed: {e}")
    return

  # Get all documents in the collection
  collection_ref = db.collection("historical_figures")
  docs = collection_ref.stream()

  # Separate initial from non-initial figures
  doc_list = list(docs)
  initial_docs = []
  non_initial_docs = []

  for doc in doc_list:
    data = doc.to_dict()
    # Check if initial field exists and is True
    if data.get("initial", False) is True:
      initial_docs.append(doc)
    else:
      non_initial_docs.append(doc)

  total_docs = len(doc_list)
  initial_count = len(initial_docs)
  non_initial_count = len(non_initial_docs)

  print(f"\n{'='*60}")
  print(f"Total documents: {total_docs}")
  print(f"  Initial figures (will be preserved): {initial_count}")
  print(f"  Non-initial figures (will be deleted): {non_initial_count}")
  print(f"{'='*60}\n")

  if non_initial_count == 0:
    print("No non-initial documents to delete.")
    return

  response = input(f"Delete {non_initial_count} non-initial documents? (yes/no): ")

  if response.lower() != "yes":
    print("Deletion cancelled.")
    return

  # Delete non-initial documents
  print("\nDeleting non-initial documents...")
  deleted_count = 0

  for doc in non_initial_docs:
    try:
      doc.reference.delete()
      deleted_count += 1
      if deleted_count % 10 == 0:
        print(f"  Deleted {deleted_count}/{non_initial_count} documents...")
    except Exception as e:
      print(f"  Error deleting {doc.id}: {e}")

  print(f"\n{'='*60}")
  print(f"✓ Successfully deleted {deleted_count} non-initial documents")
  print(f"✓ Preserved {initial_count} initial figures")
  print(f"{'='*60}")


if __name__ == "__main__":
  clear_all_figures()

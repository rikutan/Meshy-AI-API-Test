import os
import firebase_admin
from firebase_admin import credentials, firestore, storage

_app = None
_db = None
_bucket = None

def init_firebase():
    global _app, _db, _bucket
    if _app is not None:
        return _db, _bucket

    project_id = os.getenv("FIREBASE_PROJECT_ID")
    bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    cred = credentials.Certificate(cred_path)
    _app = firebase_admin.initialize_app(cred, {
        "storageBucket": bucket_name,
        "projectId": project_id
    })
    _db = firestore.client()
    _bucket = storage.bucket()
    return _db, _bucket

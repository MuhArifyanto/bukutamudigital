import logging
import os
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Tamu
import firebase_admin
from firebase_admin import auth

logger = logging.getLogger(__name__)

@receiver(post_delete, sender=Tamu)
def delete_firebase_user(sender, instance, **kwargs):
    """
    Signal to delete a user from Firebase Auth when their record is deleted in MySQL.
    """
    uid = instance.google_id
    email = instance.email
    
    if not uid and not email:
        logger.info("Skip Firebase deletion: No google_id or email found on Tamu instance.")
        return
        
    try:
        # Initialize Firebase Admin SDK if not already initialized
        if not firebase_admin._apps:
            cred_path = os.path.join(os.path.dirname(__file__), '../firebase_credentials.json')
            if os.path.exists(cred_path):
                cred = firebase_admin.credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin SDK initialized using firebase_credentials.json")
            else:
                firebase_admin.initialize_app()
                logger.info("Firebase Admin SDK initialized using default credentials")
                
        # 1. Delete by UID if exists
        if uid:
            try:
                auth.delete_user(uid)
                logger.info(f"Successfully deleted Firebase user by UID: {uid}")
                return
            except auth.UserNotFoundError:
                logger.warning(f"Firebase user not found by UID: {uid}. Trying lookup by email...")
            except Exception as e:
                logger.error(f"Failed to delete Firebase user by UID: {uid}. Error: {str(e)}")
                
        # 2. Fallback to delete by Email
        if email:
            try:
                user = auth.get_user_by_email(email)
                auth.delete_user(user.uid)
                logger.info(f"Successfully deleted Firebase user by Email: {email} (UID: {user.uid})")
            except auth.UserNotFoundError:
                logger.warning(f"Firebase user not found by Email: {email}")
            except Exception as e:
                logger.error(f"Failed to delete Firebase user by Email: {email}. Error: {str(e)}")
                
    except Exception as e:
        logger.error(f"Error syncing deletion to Firebase for user {email}: {str(e)}")

"""
Utility Functions Module
"""
import random
import string
import logging

def get_logger(name):
    """
    Get a logger instance.
    """
    return logging.getLogger(name)

def gen_session_id(type='xs'):
    """
    Generate a session ID.

    Args:
        type: Session type prefix

    Returns:
        str: Generated session ID
    """
    chars = string.ascii_letters + string.digits
    random_str = ''.join(random.choice(chars) for _ in range(12))
    return f"{type}_{random_str}"

def gen_auth_cookies(session_id='', signature=''):
    """
    Generate authentication cookies.

    Args:
        session_id: Session ID
        signature: Signature

    Returns:
        str: Auth cookie string
    """
    if not session_id:
        return ''
    if not signature:
        return f'sessionid={session_id}'
    return f'sessionid={session_id};sessionid_sign={signature}'

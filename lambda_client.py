"""
AWS Lambda client for email classification
Routes classification requests to AWS Lambda instead of OpenAI directly
"""
import json
import os
from typing import Dict, List, Tuple, Optional

# Try to import boto3 (optional - will fail gracefully if not available)
try:
    import boto3
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    boto3 = None

from auth import encrypt_token, decrypt_token
from cryptography.fernet import Fernet
import base64


class LambdaClient:
    """Client for calling AWS Lambda email classification function"""
    
    def __init__(self):
        try:
            # Check if boto3 is available
            if not BOTO3_AVAILABLE or boto3 is None:
                raise ValueError("boto3 is not installed. Install it with: pip install boto3")
            
            self.function_arn = os.getenv('LAMBDA_FUNCTION_ARN')
            self.region = os.getenv('AWS_REGION', 'us-east-1')
            self.aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
            self.aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
            
            if not self.function_arn:
                raise ValueError("LAMBDA_FUNCTION_ARN environment variable not set")
            
            if not self.aws_access_key_id or not self.aws_secret_access_key:
                raise ValueError("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables not set")
            
            # Initialize Lambda client
            try:
                self.lambda_client = boto3.client(
                    'lambda',
                    region_name=self.region,
                    aws_access_key_id=self.aws_access_key_id,
                    aws_secret_access_key=self.aws_secret_access_key
                )
            except Exception as e:
                raise ValueError(f"Failed to initialize Lambda client: {str(e)}")
            
            # Get encryption key for one-time encryption
            encryption_key = os.getenv('ENCRYPTION_KEY')
            if not encryption_key:
                raise ValueError("ENCRYPTION_KEY environment variable not set")
            
            # Use the same encryption logic as auth.py
            try:
                from auth import get_cipher
                self.cipher = get_cipher()
            except Exception as e:
                raise ValueError(f"Failed to initialize encryption cipher: {str(e)}")
        except Exception as e:
            # Re-raise with clear error message
            raise ValueError(f"LambdaClient initialization failed: {str(e)}")
    
    def _encrypt_email_data(self, email_data: Dict) -> Tuple[str, str]:
        """
        Encrypt email data for Lambda
        Returns: (encrypted_content, one_time_key)
        """
        # Generate a one-time encryption key for this request
        one_time_key = Fernet.generate_key().decode()
        one_time_cipher = Fernet(one_time_key.encode())
        
        # Serialize email data
        email_json = json.dumps(email_data)
        
        # Encrypt with one-time key
        encrypted = one_time_cipher.encrypt(email_json.encode())
        encrypted_content = encrypted.decode()
        
        return encrypted_content, one_time_key
    
    def classify_email(
        self,
        subject: str,
        body: str,
        headers: Dict[str, str],
        sender: str,
        links: List[str],
        deterministic_category: str,
        has_pdf_attachment: bool = False,
        thread_id: str = None,
        user_id: str = None
    ) -> Tuple[str, float]:
        """
        Classify email using AWS Lambda
        Returns: (category, confidence)
        """
        try:
            # Prepare email data
            email_data = {
                'subject': subject,
                'body': body,
                'sender': sender,
                'headers': headers,
                'links': links,
                'deterministic_category': deterministic_category,
                'has_pdf_attachment': has_pdf_attachment
            }
            
            # Encrypt email data
            encrypted_email, one_time_key = self._encrypt_email_data(email_data)
            
            # Get user encryption key (for result encryption)
            # Use the same encryption key format as auth.py
            from auth import get_cipher
            user_cipher = get_cipher()
            # We'll pass the raw ENCRYPTION_KEY string to Lambda, which will use it to create its own cipher
            user_key = os.getenv('ENCRYPTION_KEY')
            
            # Prepare Lambda payload
            payload = {
                'encrypted_email': encrypted_email,
                'encryption_key': one_time_key,  # One-time key for decryption
                'user_encryption_key': user_key,  # User's key for result encryption
                'thread_id': thread_id or 'unknown',
                'user_id': user_id or 'unknown'
            }
            
            # Invoke Lambda function
            response = self.lambda_client.invoke(
                FunctionName=self.function_arn,
                InvocationType='RequestResponse',  # Synchronous
                Payload=json.dumps(payload)
            )
            
            # Parse response
            response_payload = json.loads(response['Payload'].read())
            
            if response_payload.get('statusCode') != 200:
                error_msg = response_payload.get('body', 'Unknown error')
                raise Exception(f"Lambda error: {error_msg}")
            
            body_data = json.loads(response_payload['body'])
            
            if not body_data.get('success'):
                raise Exception(f"Classification failed: {body_data.get('error', 'Unknown error')}")
            
            # Decrypt result
            encrypted_result = body_data['encrypted_result']
            decrypted_result = self.cipher.decrypt(encrypted_result.encode())
            result_data = json.loads(decrypted_result.decode())
            
            # Extract category and confidence
            label = result_data.get('label', '').lower()
            confidence = float(result_data.get('confidence', 0.75))
            
            # Map label to category constant
            category_map = {
                'dealflow': 'DEAL_FLOW',
                'deal flow': 'DEAL_FLOW',
                'hiring': 'HIRING',
                'networking': 'NETWORKING',
                'spam': 'SPAM',
                'general': 'GENERAL'
            }
            
            category = category_map.get(label, 'GENERAL')
            
            return (category, confidence)
            
        except Exception as e:
            print(f"Error calling Lambda: {str(e)}")
            # Fallback to deterministic classification
            return (deterministic_category, 0.5)
    
    def generate_scheduled_email(
        self,
        subject: str,
        body: str,
        sender: str,
        founder_name: str = None,
        thread_id: str = None,
        user_id: str = None
    ) -> str:
        """
        Generate scheduled email using Lambda/Kimi AI
        Returns: Generated email body (HTML)
        """
        try:
            # Prepare email data
            email_data = {
                'subject': subject,
                'body': body[:5000],  # Limit body length
                'sender': sender,
                'founder_name': founder_name or ''
            }
            
            # Encrypt email data with one-time key
            encrypted_email, one_time_key = self._encrypt_email_data(email_data)
            
            # Get user encryption key for result encryption
            user_key = os.getenv('ENCRYPTION_KEY')
            
            # Prepare Lambda payload
            payload = {
                'encrypted_email': encrypted_email,
                'encryption_key': one_time_key,  # One-time key for decryption
                'user_encryption_key': user_key,  # User's key for result encryption
                'thread_id': thread_id or 'unknown',
                'user_id': user_id or 'unknown',
                'action': 'generate_email'  # Tell Lambda this is email generation
            }
            
            # Invoke Lambda function
            response = self.lambda_client.invoke(
                FunctionName=self.function_arn,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            # Parse response
            response_payload = json.loads(response['Payload'].read())
            
            if response_payload.get('statusCode') != 200:
                error_msg = response_payload.get('body', 'Unknown error')
                raise Exception(f"Lambda error: {error_msg}")
            
            body_data = json.loads(response_payload['body'])
            
            if not body_data.get('success'):
                raise Exception(f"Email generation failed: {body_data.get('error', 'Unknown error')}")
            
            # Decrypt result
            encrypted_result = body_data['encrypted_email_body']
            decrypted_result = self.cipher.decrypt(encrypted_result.encode())
            
            return decrypted_result.decode()
            
        except Exception as e:
            print(f"Error calling Lambda for email generation: {str(e)}")
            raise


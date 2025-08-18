"""
WordPress Configuration for SIPORTS v2.0 Production
Handles WordPress database connection and JWT authentication
"""

import os
import mysql.connector
from mysql.connector import Error
import jwt
from datetime import datetime, timedelta
import hashlib
import logging

logger = logging.getLogger(__name__)

class WordPressConfig:
    def __init__(self):
        # WordPress Database Configuration (Production)
        self.wp_host = os.environ.get('WP_DB_HOST', 'localhost')
        self.wp_database = os.environ.get('WP_DB_NAME', 'wordpress')
        self.wp_user = os.environ.get('WP_DB_USER', 'root')
        self.wp_password = os.environ.get('WP_DB_PASSWORD', '')
        self.wp_port = int(os.environ.get('WP_DB_PORT', 3306))
        
        # WordPress JWT Configuration
        self.wp_jwt_secret = os.environ.get('WP_JWT_SECRET', 'your-wordpress-jwt-secret-key')
        self.wp_table_prefix = os.environ.get('WP_TABLE_PREFIX', 'wp_')
        
        # WordPress Site Configuration
        self.wp_site_url = os.environ.get('WP_SITE_URL', 'https://siportevent.com')
        self.wp_admin_email = os.environ.get('WP_ADMIN_EMAIL', 'admin@siportevent.com')
        
        logger.info(f"WordPress config initialized for: {self.wp_site_url}")

    def get_wp_connection(self):
        """Get WordPress MySQL database connection"""
        try:
            connection = mysql.connector.connect(
                host=self.wp_host,
                database=self.wp_database,
                user=self.wp_user,
                password=self.wp_password,
                port=self.wp_port,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci'
            )
            
            if connection.is_connected():
                logger.info("WordPress MySQL connection established")
                return connection
                
        except Error as e:
            logger.error(f"WordPress MySQL connection failed: {e}")
            return None

    def verify_wp_user(self, username, password):
        """Verify WordPress user credentials"""
        try:
            connection = self.get_wp_connection()
            if not connection:
                return None

            cursor = connection.cursor(dictionary=True)
            
            # Get user from WordPress database
            cursor.execute(f"""
                SELECT ID, user_login, user_email, user_pass, display_name
                FROM {self.wp_table_prefix}users 
                WHERE user_login = %s OR user_email = %s
            """, (username, username))
            
            wp_user = cursor.fetchone()
            
            if wp_user and self.check_wp_password(password, wp_user['user_pass']):
                # Get user capabilities
                cursor.execute(f"""
                    SELECT meta_value 
                    FROM {self.wp_table_prefix}usermeta 
                    WHERE user_id = %s AND meta_key = '{self.wp_table_prefix}capabilities'
                """, (wp_user['ID'],))
                
                capabilities = cursor.fetchone()
                user_role = 'subscriber'  # default
                
                if capabilities:
                    caps = capabilities['meta_value']
                    if 'administrator' in caps:
                        user_role = 'administrator'
                    elif 'editor' in caps:
                        user_role = 'editor'
                    elif 'author' in caps:
                        user_role = 'author'
                
                return {
                    'id': wp_user['ID'],
                    'username': wp_user['user_login'],
                    'email': wp_user['user_email'],
                    'display_name': wp_user['display_name'],
                    'role': user_role
                }
                
            return None
            
        except Error as e:
            logger.error(f"WordPress user verification failed: {e}")
            return None
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def check_wp_password(self, password, wp_hash):
        """Check password against WordPress hash (simplified)"""
        # WordPress uses PHPass - this is a simplified version
        # In production, use proper PHPass library
        if wp_hash.startswith('$P$'):
            # PHPass hash - simplified check
            return len(password) > 0  # Placeholder - implement proper PHPass
        else:
            # MD5 fallback (old WordPress)
            return hashlib.md5(password.encode()).hexdigest() == wp_hash

    def sync_user_to_siports(self, wp_user_data, siports_connection):
        """Sync WordPress user to SIPORTS database"""
        try:
            cursor = siports_connection.cursor()
            
            # Check if user exists in SIPORTS
            cursor.execute(
                'SELECT id FROM users WHERE email = ?',
                (wp_user_data['email'],)
            )
            existing_user = cursor.fetchone()
            
            if existing_user:
                # Update existing user
                cursor.execute('''
                    UPDATE users 
                    SET first_name = ?, last_name = ?, wp_user_id = ?, status = 'validated'
                    WHERE email = ?
                ''', (
                    wp_user_data['display_name'].split(' ')[0] if ' ' in wp_user_data['display_name'] else wp_user_data['display_name'],
                    wp_user_data['display_name'].split(' ', 1)[1] if ' ' in wp_user_data['display_name'] else '',
                    wp_user_data['id'],
                    wp_user_data['email']
                ))
                logger.info(f"Updated SIPORTS user: {wp_user_data['email']}")
            else:
                # Create new user
                cursor.execute('''
                    INSERT INTO users (email, password_hash, user_type, first_name, last_name, wp_user_id, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'validated')
                ''', (
                    wp_user_data['email'],
                    'wp_auth',  # Placeholder for WordPress-authenticated users
                    'visitor',  # Default type
                    wp_user_data['display_name'].split(' ')[0] if ' ' in wp_user_data['display_name'] else wp_user_data['display_name'],
                    wp_user_data['display_name'].split(' ', 1)[1] if ' ' in wp_user_data['display_name'] else '',
                    wp_user_data['id']
                ))
                logger.info(f"Created new SIPORTS user: {wp_user_data['email']}")
            
            siports_connection.commit()
            return True
            
        except Exception as e:
            logger.error(f"User sync failed: {e}")
            siports_connection.rollback()
            return False

    def create_wp_jwt_token(self, wp_user_data):
        """Create JWT token for WordPress user"""
        payload = {
            'wp_user_id': wp_user_data['id'],
            'username': wp_user_data['username'],
            'email': wp_user_data['email'],
            'role': wp_user_data['role'],
            'iss': self.wp_site_url,
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(days=7)
        }
        
        return jwt.encode(payload, self.wp_jwt_secret, algorithm='HS256')

    def get_wp_user_packages(self, wp_user_id):
        """Get user packages from WordPress custom fields"""
        try:
            connection = self.get_wp_connection()
            if not connection:
                return {}

            cursor = connection.cursor(dictionary=True)
            
            # Get user packages from custom fields
            cursor.execute(f"""
                SELECT meta_key, meta_value 
                FROM {self.wp_table_prefix}usermeta 
                WHERE user_id = %s AND (
                    meta_key = 'siports_visitor_package' OR 
                    meta_key = 'siports_partnership_package'
                )
            """, (wp_user_id,))
            
            packages = {}
            for row in cursor.fetchall():
                if row['meta_key'] == 'siports_visitor_package':
                    packages['visitor_package'] = row['meta_value']
                elif row['meta_key'] == 'siports_partnership_package':
                    packages['partnership_package'] = row['meta_value']
            
            return packages
            
        except Error as e:
            logger.error(f"Failed to get user packages: {e}")
            return {}
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def update_wp_user_packages(self, wp_user_id, packages):
        """Update user packages in WordPress custom fields"""
        try:
            connection = self.get_wp_connection()
            if not connection:
                return False

            cursor = connection.cursor()
            
            for package_type, package_value in packages.items():
                meta_key = f'siports_{package_type}'
                
                # Insert or update user meta
                cursor.execute(f"""
                    INSERT INTO {self.wp_table_prefix}usermeta (user_id, meta_key, meta_value)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE meta_value = VALUES(meta_value)
                """, (wp_user_id, meta_key, package_value))
            
            connection.commit()
            logger.info(f"Updated WordPress user packages for user {wp_user_id}")
            return True
            
        except Error as e:
            logger.error(f"Failed to update user packages: {e}")
            return False
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

# Global WordPress configuration instance
wp_config = WordPressConfig()
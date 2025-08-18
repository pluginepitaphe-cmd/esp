"""
WordPress Synchronization Service for SIPORTS v2.0
Handles bidirectional sync between WordPress and SIPORTS
"""

import sqlite3
import logging
from datetime import datetime
from wordpress_config import wp_config
import json

logger = logging.getLogger(__name__)

class WordPressSyncService:
    def __init__(self, siports_db_path):
        self.siports_db_path = siports_db_path
        self.wp_config = wp_config

    def get_siports_connection(self):
        """Get SIPORTS SQLite connection"""
        try:
            conn = sqlite3.connect(self.siports_db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            logger.error(f"SIPORTS database connection failed: {e}")
            return None

    def sync_wp_user_to_siports(self, wp_username, password):
        """Sync WordPress user to SIPORTS on login"""
        try:
            # Verify WordPress user
            wp_user = self.wp_config.verify_wp_user(wp_username, password)
            if not wp_user:
                return None

            # Get SIPORTS connection
            siports_conn = self.get_siports_connection()
            if not siports_conn:
                return None

            # Sync user data
            success = self.wp_config.sync_user_to_siports(wp_user, siports_conn)
            if not success:
                return None

            # Get updated SIPORTS user
            cursor = siports_conn.cursor()
            cursor.execute(
                'SELECT * FROM users WHERE email = ?',
                (wp_user['email'],)
            )
            siports_user = cursor.fetchone()
            siports_conn.close()

            if siports_user:
                # Get WordPress packages
                wp_packages = self.wp_config.get_wp_user_packages(wp_user['id'])
                
                # Merge user data
                user_data = dict(siports_user)
                user_data.update(wp_packages)
                user_data['wp_user_id'] = wp_user['id']
                user_data['wp_role'] = wp_user['role']

                logger.info(f"Successfully synced WordPress user: {wp_user['email']}")
                return user_data

            return None

        except Exception as e:
            logger.error(f"WordPress user sync failed: {e}")
            return None

    def sync_siports_packages_to_wp(self, user_id, packages):
        """Sync SIPORTS package updates to WordPress"""
        try:
            # Get SIPORTS user
            siports_conn = self.get_siports_connection()
            if not siports_conn:
                return False

            cursor = siports_conn.cursor()
            cursor.execute(
                'SELECT wp_user_id FROM users WHERE id = ?',
                (user_id,)
            )
            user = cursor.fetchone()
            siports_conn.close()

            if not user or not user['wp_user_id']:
                logger.warning(f"No WordPress user ID found for SIPORTS user {user_id}")
                return False

            # Update WordPress user packages
            wp_packages = {}
            if 'visitor_package' in packages:
                wp_packages['visitor_package'] = packages['visitor_package']
            if 'partnership_package' in packages:
                wp_packages['partnership_package'] = packages['partnership_package']

            success = self.wp_config.update_wp_user_packages(user['wp_user_id'], wp_packages)
            
            if success:
                logger.info(f"Successfully synced packages to WordPress for user {user_id}")
            
            return success

        except Exception as e:
            logger.error(f"Package sync to WordPress failed: {e}")
            return False

    def get_wp_events_data(self):
        """Get events data from WordPress custom post types"""
        try:
            connection = self.wp_config.get_wp_connection()
            if not connection:
                return []

            cursor = connection.cursor(dictionary=True)
            
            # Get events from WordPress (assuming custom post type 'siports_event')
            cursor.execute(f"""
                SELECT p.ID, p.post_title, p.post_content, p.post_date, p.post_status,
                       pm1.meta_value as event_date,
                       pm2.meta_value as event_location,
                       pm3.meta_value as event_type
                FROM {self.wp_config.wp_table_prefix}posts p
                LEFT JOIN {self.wp_config.wp_table_prefix}postmeta pm1 ON p.ID = pm1.post_id AND pm1.meta_key = 'event_date'
                LEFT JOIN {self.wp_config.wp_table_prefix}postmeta pm2 ON p.ID = pm2.post_id AND pm2.meta_key = 'event_location'  
                LEFT JOIN {self.wp_config.wp_table_prefix}postmeta pm3 ON p.ID = pm3.post_id AND pm3.meta_key = 'event_type'
                WHERE p.post_type = 'siports_event' AND p.post_status = 'publish'
                ORDER BY p.post_date DESC
                LIMIT 50
            """)
            
            events = []
            for row in cursor.fetchall():
                events.append({
                    'id': row['ID'],
                    'title': row['post_title'],
                    'content': row['post_content'],
                    'date': row['event_date'] or row['post_date'],
                    'location': row['event_location'] or 'SIPORTS Event',
                    'type': row['event_type'] or 'conference',
                    'status': row['post_status']
                })
            
            logger.info(f"Retrieved {len(events)} events from WordPress")
            return events

        except Exception as e:
            logger.error(f"Failed to get WordPress events: {e}")
            return []
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_wp_exhibitors_data(self):
        """Get exhibitors data from WordPress"""
        try:
            connection = self.wp_config.get_wp_connection()
            if not connection:
                return []

            cursor = connection.cursor(dictionary=True)
            
            # Get exhibitors from WordPress (assuming custom post type 'siports_exhibitor')
            cursor.execute(f"""
                SELECT p.ID, p.post_title, p.post_content, p.post_excerpt,
                       pm1.meta_value as company_website,
                       pm2.meta_value as company_sector,
                       pm3.meta_value as company_logo,
                       pm4.meta_value as booth_number
                FROM {self.wp_config.wp_table_prefix}posts p
                LEFT JOIN {self.wp_config.wp_table_prefix}postmeta pm1 ON p.ID = pm1.post_id AND pm1.meta_key = 'company_website'
                LEFT JOIN {self.wp_config.wp_table_prefix}postmeta pm2 ON p.ID = pm2.post_id AND pm2.meta_key = 'company_sector'
                LEFT JOIN {self.wp_config.wp_table_prefix}postmeta pm3 ON p.ID = pm3.post_id AND pm3.meta_key = 'company_logo'
                LEFT JOIN {self.wp_config.wp_table_prefix}postmeta pm4 ON p.ID = pm4.post_id AND pm4.meta_key = 'booth_number'
                WHERE p.post_type = 'siports_exhibitor' AND p.post_status = 'publish'
                ORDER BY p.post_title
            """)
            
            exhibitors = []
            for row in cursor.fetchall():
                exhibitors.append({
                    'id': row['ID'],
                    'name': row['post_title'],
                    'description': row['post_content'] or row['post_excerpt'],
                    'website': row['company_website'],
                    'sector': row['company_sector'] or 'Maritime',
                    'logo': row['company_logo'],
                    'booth': row['booth_number']
                })
            
            logger.info(f"Retrieved {len(exhibitors)} exhibitors from WordPress")
            return exhibitors

        except Exception as e:
            logger.error(f"Failed to get WordPress exhibitors: {e}")
            return []
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def webhook_handler(self, webhook_data):
        """Handle WordPress webhooks for real-time sync"""
        try:
            action = webhook_data.get('action')
            post_type = webhook_data.get('post_type')
            post_id = webhook_data.get('post_id')

            logger.info(f"Processing WordPress webhook: {action} for {post_type} ID {post_id}")

            if action == 'user_register':
                # Handle new user registration
                return self._handle_user_registration_webhook(webhook_data)
            
            elif action == 'user_meta_update':
                # Handle user package updates
                return self._handle_user_meta_webhook(webhook_data)
            
            elif action in ['publish_post', 'update_post'] and post_type in ['siports_event', 'siports_exhibitor']:
                # Handle event/exhibitor updates
                return self._handle_content_webhook(webhook_data)

            return {"status": "ignored", "message": f"Webhook action {action} not handled"}

        except Exception as e:
            logger.error(f"Webhook processing failed: {e}")
            return {"status": "error", "message": str(e)}

    def _handle_user_registration_webhook(self, data):
        """Handle user registration webhook"""
        try:
            user_email = data.get('user_email')
            if not user_email:
                return {"status": "error", "message": "No user email provided"}

            # Sync new WordPress user to SIPORTS
            # This will be called when user registers on WordPress
            logger.info(f"New WordPress user registered: {user_email}")
            
            return {"status": "success", "message": "User registration webhook processed"}

        except Exception as e:
            logger.error(f"User registration webhook failed: {e}")
            return {"status": "error", "message": str(e)}

    def _handle_user_meta_webhook(self, data):
        """Handle user meta update webhook"""
        try:
            wp_user_id = data.get('user_id')
            meta_key = data.get('meta_key')
            meta_value = data.get('meta_value')

            if meta_key in ['siports_visitor_package', 'siports_partnership_package']:
                # Sync package changes back to SIPORTS
                siports_conn = self.get_siports_connection()
                if siports_conn:
                    cursor = siports_conn.cursor()
                    
                    package_field = meta_key.replace('siports_', '')
                    cursor.execute(
                        f'UPDATE users SET {package_field} = ? WHERE wp_user_id = ?',
                        (meta_value, wp_user_id)
                    )
                    siports_conn.commit()
                    siports_conn.close()

                    logger.info(f"Synced WordPress package update: {meta_key} = {meta_value}")

            return {"status": "success", "message": "User meta webhook processed"}

        except Exception as e:
            logger.error(f"User meta webhook failed: {e}")
            return {"status": "error", "message": str(e)}

    def _handle_content_webhook(self, data):
        """Handle content update webhook"""
        try:
            post_type = data.get('post_type')
            post_id = data.get('post_id')

            # Log content updates (could trigger cache refresh, notifications, etc.)
            logger.info(f"WordPress content updated: {post_type} ID {post_id}")

            return {"status": "success", "message": "Content webhook processed"}

        except Exception as e:
            logger.error(f"Content webhook failed: {e}")
            return {"status": "error", "message": str(e)}

# Global sync service instance
wp_sync_service = None

def get_wp_sync_service(db_path):
    """Get WordPress sync service instance"""
    global wp_sync_service
    if wp_sync_service is None:
        wp_sync_service = WordPressSyncService(db_path)
    return wp_sync_service
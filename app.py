from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
from pymongo import MongoClient
import bcrypt
import jwt
import requests
from datetime import datetime, timedelta
import os
import re
import random
import string

# ========== CONFIGURATION ==========
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Debug info
print("=" * 60)
print("🚀 SORTLI.ME BACKEND v3.2")
print("=" * 60)

# Get environment variables
MONGO_URI = os.getenv('MONGO_URL')
JWT_SECRET = os.getenv('JWT_SECRET', 'default-secret-change-in-production')
IPINFO_TOKEN = os.getenv('IPINFO_TOKEN', '')

print(f"📡 MONGO_URI: {'✅ Found' if MONGO_URI else '❌ Missing'}")
print(f"🔑 JWT_SECRET: {'✅ Set' if JWT_SECRET != 'default-secret-change-in-production' else '⚠️ Using default'}")
print(f"🌐 IPINFO_TOKEN: {'✅ Set' if IPINFO_TOKEN else '❌ Not set'}")

# ========== DATABASE CONNECTION ==========
db = None
if MONGO_URI:
    try:
        print("\n🔗 Connecting to MongoDB...")
        
        # Fix Railway MongoDB URI (add database name)
        if 'mongodb.railway.internal' in MONGO_URI or 'mongo:' in MONGO_URI:
            print("   Detected Railway MongoDB format")
            if '?' in MONGO_URI:
                base, query = MONGO_URI.split('?', 1)
                FIXED_URI = f"{base}/sortli?{query}"
            else:
                FIXED_URI = f"{MONGO_URI}/sortli?authSource=admin"
        else:
            FIXED_URI = MONGO_URI
        
        print(f"   Using URI: {FIXED_URI[:60]}...")
        
        # Connect with timeout
        client = MongoClient(FIXED_URI, serverSelectionTimeoutMS=10000)
        
        # Test connection
        client.admin.command('ping')
        print("✅ MongoDB connected!")
        
        # Get database (always use 'sortli' for Railway)
        db_name = 'sortli'
        db = client[db_name]
        print(f"📁 Using database: '{db_name}'")
        
        # Create collections if they don't exist
        collections = db.list_collection_names()
        print(f"📊 Collections: {collections}")
        
        for col in ['users', 'urls', 'clicks']:
            if col not in collections:
                db.create_collection(col)
                print(f"   Created: {col}")
        
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        db = None
else:
    print("❌ No MongoDB URI found")
    db = None

print("=" * 60)

# ========== HELPER FUNCTIONS ==========
def get_location_from_ip(ip_address):
    """Get location from IP address"""
    if not ip_address or ip_address in ['127.0.0.1', 'localhost', '::1']:
        return {'country': 'Local', 'city': 'Local', 'region': 'Local'}
    
    try:
        if IPINFO_TOKEN:
            url = f'https://ipinfo.io/{ip_address}/json?token={IPINFO_TOKEN}'
        else:
            url = f'https://ipinfo.io/{ip_address}/json'
        
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            return {
                'country': data.get('country', 'Unknown'),
                'city': data.get('city', 'Unknown'),
                'region': data.get('region', 'Unknown'),
                'timezone': data.get('timezone', 'Unknown')
            }
    except:
        pass
    
    return {'country': 'Unknown', 'city': 'Unknown', 'region': 'Unknown'}

def validate_url(url):
    """Validate and normalize URL"""
    if not url:
        return None
    
    # Add https:// if no protocol
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Simple validation
    pattern = r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
    if re.match(pattern, url):
        return url
    
    return None

def generate_short_code(length=6):
    """Generate random short code"""
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=length))

def get_og_metadata(url):
    """Get Open Graph metadata from URL"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        content = response.text
        
        metadata = {'title': '', 'description': '', 'image': ''}
        
        # Extract title
        title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
        if title_match:
            metadata['title'] = title_match.group(1)[:200]
        
        # Extract OG title
        og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', content, re.IGNORECASE)
        if og_title:
            metadata['title'] = og_title.group(1)[:200]
        
        # Extract description
        og_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']', content, re.IGNORECASE)
        if og_desc:
            metadata['description'] = og_desc.group(1)[:300]
        
        # Extract image
        og_image = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']', content, re.IGNORECASE)
        if og_image:
            metadata['image'] = og_image.group(1)
        
        return metadata
    except:
        return {'title': '', 'description': '', 'image': ''}

def verify_token():
    """Verify JWT token from request header"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header.split(' ')[1]
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload
    except:
        return None

# ========== CHECK DATABASE CONNECTION ==========
def check_db():
    """Check if database is connected"""
    return db is not None

# ========== ROUTES ==========
@app.route('/')
def home():
    db_connected = check_db()
    return jsonify({
        'service': 'Sortli.me URL Shortener',
        'version': '3.2',
        'status': 'online',
        'database': 'connected' if db_connected else 'disconnected',
        'timestamp': datetime.utcnow().isoformat(),
        'endpoints': ['/health', '/api/register', '/api/login', '/api/urls', '/api/analytics', '/:short_code']
    })

@app.route('/health')
def health():
    db_connected = check_db()
    return jsonify({
        'status': 'healthy' if db_connected else 'degraded',
        'database': 'connected' if db_connected else 'disconnected',
        'timestamp': datetime.utcnow().isoformat()
    })

# ========== AUTHENTICATION ==========
@app.route('/api/register', methods=['POST'])
def register():
    """Register new user"""
    if not check_db():
        return jsonify({'error': 'Database not connected'}), 500
    
    try:
        data = request.get_json()
        
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({'error': 'Username and password required'}), 400
        
        username = data['username'].strip()
        password = data['password'].strip()
        
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        # Check if user exists
        if db.users.find_one({'username': username}):
            return jsonify({'error': 'Username already exists'}), 400
        
        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # Create user
        user = {
            'username': username,
            'password_hash': password_hash.decode('utf-8'),
            'created_at': datetime.utcnow(),
            'url_count': 0,
            'total_clicks': 0,
            'plan': 'free'
        }
        
        result = db.users.insert_one(user)
        user_id = str(result.inserted_id)
        
        print(f"✅ New user: {username}")
        
        return jsonify({
            'success': True,
            'message': 'User created successfully',
            'user_id': user_id,
            'username': username
        }), 201
        
    except Exception as e:
        print(f"Register error: {e}")
        return jsonify({'error': 'Registration failed'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    """User login"""
    if not check_db():
        return jsonify({'error': 'Database not connected'}), 500
    
    try:
        data = request.get_json()
        
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({'error': 'Username and password required'}), 400
        
        username = data['username'].strip()
        password = data['password'].strip()
        
        # Find user
        user = db.users.find_one({'username': username})
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Verify password
        if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            # Create JWT token
            token = jwt.encode({
                'user_id': str(user['_id']),
                'username': user['username'],
                'exp': datetime.utcnow() + timedelta(days=7)
            }, JWT_SECRET, algorithm='HS256')
            
            return jsonify({
                'success': True,
                'token': token,
                'user_id': str(user['_id']),
                'username': user['username'],
                'url_count': user.get('url_count', 0),
                'total_clicks': user.get('total_clicks', 0)
            })
        
        return jsonify({'error': 'Invalid credentials'}), 401
        
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500

# ========== URL MANAGEMENT ==========
@app.route('/api/urls', methods=['GET'])
def get_user_urls():
    """Get all URLs for authenticated user"""
    if not check_db():
        return jsonify({'error': 'Database not connected'}), 500
    
    payload = verify_token()
    if not payload:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        user_id = payload['user_id']
        
        # Get URLs
        urls = list(db.urls.find({'user_id': user_id}).sort('created_at', -1))
        
        # Format response
        formatted_urls = []
        total_clicks = 0
        
        for url in urls:
            total_clicks += url.get('clicks', 0)
            formatted_urls.append({
                'id': str(url['_id']),
                'short_code': url['short_code'],
                'short_url': f"https://{request.host}/{url['short_code']}",
                'long_url': url['long_url'],
                'title': url.get('title', ''),
                'description': url.get('description', ''),
                'clicks': url.get('clicks', 0),
                'created_at': url['created_at'].isoformat() if isinstance(url['created_at'], datetime) else url['created_at'],
                'last_clicked': url.get('last_clicked')
            })
        
        return jsonify({
            'success': True,
            'urls': formatted_urls,
            'count': len(urls),
            'total_clicks': total_clicks
        })
        
    except Exception as e:
        print(f"Get URLs error: {e}")
        return jsonify({'error': 'Failed to get URLs'}), 500

@app.route('/api/urls', methods=['POST'])
def create_url():
    """Create new short URL"""
    if not check_db():
        return jsonify({'error': 'Database not connected'}), 500
    
    payload = verify_token()
    if not payload:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        data = request.get_json()
        
        if not data or 'long_url' not in data:
            return jsonify({'error': 'URL is required'}), 400
        
        user_id = payload['user_id']
        username = payload['username']
        
        # Validate URL
        long_url = validate_url(data['long_url'])
        if not long_url:
            return jsonify({'error': 'Invalid URL format'}), 400
        
        # Generate or use custom short code
        if 'short_code' in data and data['short_code']:
            short_code = data['short_code'].strip().lower()
            if not re.match(r'^[a-z0-9\-]{3,20}$', short_code):
                return jsonify({'error': 'Short code can only contain lowercase letters, numbers, and hyphens (3-20 chars)'}), 400
        else:
            short_code = generate_short_code()
        
        # Check if short code exists
        if db.urls.find_one({'short_code': short_code}):
            return jsonify({'error': 'Short code already in use'}), 400
        
        # Get OG metadata
        og_data = get_og_metadata(long_url)
        
        # Create URL document
        url_doc = {
            'user_id': user_id,
            'username': username,
            'long_url': long_url,
            'short_code': short_code,
            'title': og_data['title'] or data.get('title', ''),
            'description': og_data['description'] or data.get('description', ''),
            'image': og_data['image'],
            'clicks': 0,
            'created_at': datetime.utcnow(),
            'last_clicked': None,
            'is_active': True
        }
        
        # Insert into database
        result = db.urls.insert_one(url_doc)
        
        # Update user's URL count
        db.users.update_one(
            {'_id': user_id},
            {'$inc': {'url_count': 1}}
        )
        
        print(f"✅ New URL: {short_code} -> {long_url[:50]}...")
        
        return jsonify({
            'success': True,
            'message': 'URL created successfully',
            'short_url': f"https://{request.host}/{short_code}",
            'short_code': short_code,
            'id': str(result.inserted_id),
            'preview': {
                'title': url_doc['title'],
                'description': url_doc['description'],
                'image': url_doc['image']
            }
        }), 201
        
    except Exception as e:
        print(f"Create URL error: {e}")
        return jsonify({'error': 'Failed to create URL'}), 500

@app.route('/api/urls/<short_code>', methods=['DELETE'])
def delete_url(short_code):
    """Delete a short URL"""
    if not check_db():
        return jsonify({'error': 'Database not connected'}), 500
    
    payload = verify_token()
    if not payload:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        user_id = payload['user_id']
        
        # Find and delete URL
        result = db.urls.delete_one({
            'short_code': short_code,
            'user_id': user_id
        })
        
        if result.deleted_count == 0:
            return jsonify({'error': 'URL not found'}), 404
        
        # Update user's URL count
        db.users.update_one(
            {'_id': user_id},
            {'$inc': {'url_count': -1}}
        )
        
        return jsonify({
            'success': True,
            'message': 'URL deleted successfully'
        })
        
    except Exception as e:
        print(f"Delete URL error: {e}")
        return jsonify({'error': 'Failed to delete URL'}), 500

# ========== ANALYTICS ==========
@app.route('/api/analytics/<short_code>')
def get_analytics(short_code):
    """Get analytics for a short URL"""
    if not check_db():
        return jsonify({'error': 'Database not connected'}), 500
    
    payload = verify_token()
    if not payload:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        user_id = payload['user_id']
        
        # Find URL (verify ownership)
        url = db.urls.find_one({
            'short_code': short_code,
            'user_id': user_id
        })
        
        if not url:
            return jsonify({'error': 'URL not found or access denied'}), 404
        
        # Get clicks for this URL
        clicks = list(db.clicks.find({'url_id': url['_id']}).sort('timestamp', -1))
        
        # Process analytics
        countries = {}
        daily_stats = {}
        browsers = {}
        
        for click in clicks:
            # Country stats
            country = click.get('country', 'Unknown')
            countries[country] = countries.get(country, 0) + 1
            
            # Daily stats
            if isinstance(click['timestamp'], datetime):
                date_str = click['timestamp'].strftime('%Y-%m-%d')
            else:
                date_str = str(click['timestamp'])[:10]
            daily_stats[date_str] = daily_stats.get(date_str, 0) + 1
            
            # Browser stats
            ua = click.get('user_agent', '').lower()
            if 'chrome' in ua:
                browser = 'Chrome'
            elif 'firefox' in ua:
                browser = 'Firefox'
            elif 'safari' in ua:
                browser = 'Safari'
            elif 'edge' in ua:
                browser = 'Edge'
            else:
                browser = 'Other'
            browsers[browser] = browsers.get(browser, 0) + 1
        
        return jsonify({
            'success': True,
            'url': {
                'short_code': url['short_code'],
                'long_url': url['long_url'],
                'title': url.get('title', ''),
                'total_clicks': url.get('clicks', 0),
                'created_at': url['created_at'].isoformat() if isinstance(url['created_at'], datetime) else url['created_at']
            },
            'analytics': {
                'total_clicks': len(clicks),
                'today_clicks': daily_stats.get(datetime.utcnow().strftime('%Y-%m-%d'), 0),
                'top_countries': [{'country': k, 'count': v} for k, v in sorted(countries.items(), key=lambda x: x[1], reverse=True)[:10]],
                'daily_clicks': [{'date': k, 'count': v} for k, v in sorted(daily_stats.items())[-30:]],
                'browsers': [{'browser': k, 'count': v} for k, v in browsers.items()],
                'recent_clicks': [
                    {
                        'time': c['timestamp'].isoformat() if isinstance(c['timestamp'], datetime) else c['timestamp'],
                        'country': c.get('country', 'Unknown'),
                        'city': c.get('city', 'Unknown'),
                        'region': c.get('region', 'Unknown')
                    }
                    for c in clicks[:20]
                ]
            }
        })
        
    except Exception as e:
        print(f"Analytics error: {e}")
        return jsonify({'error': 'Failed to get analytics'}), 500

# ========== DASHBOARD ==========
@app.route('/api/dashboard')
def dashboard():
    """Get user dashboard stats"""
    if not check_db():
        return jsonify({'error': 'Database not connected'}), 500
    
    payload = verify_token()
    if not payload:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        user_id = payload['user_id']
        
        # Get user
        user = db.users.find_one({'_id': user_id})
        
        # Get URLs
        urls = list(db.urls.find({'user_id': user_id}))
        
        # Calculate stats
        total_urls = len(urls)
        total_clicks = sum(url.get('clicks', 0) for url in urls)
        
        # Get today's clicks
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_clicks = db.clicks.count_documents({
            'url_id': {'$in': [url['_id'] for url in urls]},
            'timestamp': {'$gte': today_start}
        })
        
        # Get top URLs
        top_urls = sorted(urls, key=lambda x: x.get('clicks', 0), reverse=True)[:5]
        
        return jsonify({
            'success': True,
            'stats': {
                'total_urls': total_urls,
                'total_clicks': total_clicks,
                'today_clicks': today_clicks,
                'avg_clicks_per_url': round(total_clicks / max(total_urls, 1), 1)
            },
            'top_urls': [
                {
                    'short_code': url['short_code'],
                    'title': url.get('title', 'No title')[:50],
                    'clicks': url.get('clicks', 0),
                    'short_url': f"https://{request.host}/{url['short_code']}"
                }
                for url in top_urls
            ]
        })
        
    except Exception as e:
        print(f"Dashboard error: {e}")
        return jsonify({'error': 'Failed to get dashboard'}), 500

# ========== OG PREVIEW ==========
@app.route('/api/og-preview')
def og_preview():
    """Get Open Graph metadata for a URL"""
    url = request.args.get('url')
    
    if not url:
        return jsonify({'error': 'URL parameter required'}), 400
    
    try:
        validated_url = validate_url(url)
        if not validated_url:
            return jsonify({'error': 'Invalid URL'}), 400
        
        metadata = get_og_metadata(validated_url)
        
        return jsonify({
            'success': True,
            'url': validated_url,
            'metadata': metadata
        })
        
    except Exception as e:
        print(f"OG preview error: {e}")
        return jsonify({'error': 'Failed to fetch metadata'}), 500

# ========== PUBLIC REDIRECTION ==========
@app.route('/<short_code>')
def redirect_url(short_code):
    """Public URL redirection with tracking"""
    if not check_db():
        # Still redirect if URL is known, but don't track
        return jsonify({'error': 'Service temporarily unavailable'}), 503
    
    try:
        # Find URL
        url = db.urls.find_one({
            'short_code': short_code,
            'is_active': True
        })
        
        if not url:
            return jsonify({'error': 'Short URL not found'}), 404
        
        # Get client IP
        if request.headers.get('X-Forwarded-For'):
            ip_address = request.headers.get('X-Forwarded-For').split(',')[0]
        else:
            ip_address = request.remote_addr
        
        # Get location
        location = get_location_from_ip(ip_address)
        
        # Create click record
        click_data = {
            'url_id': url['_id'],
            'short_code': short_code,
            'timestamp': datetime.utcnow(),
            'ip_address': ip_address,
            'user_agent': request.headers.get('User-Agent', ''),
            'country': location['country'],
            'city': location['city'],
            'region': location['region'],
            'referrer': request.headers.get('Referer', '')
        }
        
        # Save click
        db.clicks.insert_one(click_data)
        
        # Update URL stats
        db.urls.update_one(
            {'_id': url['_id']},
            {
                '$inc': {'clicks': 1},
                '$set': {'last_clicked': datetime.utcnow()}
            }
        )
        
        # Update user stats
        db.users.update_one(
            {'_id': url['user_id']},
            {'$inc': {'total_clicks': 1}}
        )
        
        print(f"📍 Click: {short_code} from {location['country']}")
        
        # Redirect to original URL
        return redirect(url['long_url'])
        
    except Exception as e:
        print(f"Redirect error: {e}")
        # Still try to redirect even if tracking fails
        if 'url' in locals():
            return redirect(url['long_url'])
        return jsonify({'error': 'Internal server error'}), 500

# ========== START SERVER ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    db_connected = check_db()
    print(f"\n🌍 Server starting on port {port}")
    print(f"📊 Database: {'✅ CONNECTED' if db_connected else '❌ DISCONNECTED'}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
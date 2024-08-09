from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify, abort
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import os
import boto3
from boto3.dynamodb.conditions import Key
import json
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)

app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'  # Using SQLite for simplicity
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)  # Use password_hash for storage

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)
    
# login_manager = LoginManager()
# login_manager.init_app(app)

# # User class to store user data
# class User(UserMixin):
#     def __init__(self, id, username, password):
#         self.id = id
#         self.username = username
#         self.password = generate_password_hash(password, method='pbkdf2:sha256')  # Hash the password

#     def verify_password(self, password):
#         return check_password_hash(self.password, password)

# Example users (you might replace this with a database later)


# users = {
#     User('user1', 'password1'),
#     User('user2', 'password2'),
# }

# Initialize S3 client
s3_client = boto3.client('s3')
bucket_name = 'aks3rest'  # Replace with your S3 bucket name

# Function to read JSON file from S3
def read_json_from_s3(bucket, key):
    s3_object = s3_client.get_object(Bucket=bucket, Key=key)
    json_data = s3_object['Body'].read().decode('utf-8')
    return json.loads(json_data)


# Load the JSON data from S3
restaurants_data = read_json_from_s3(bucket_name, 'R_FinalRestaurants.json')
inspections_data = read_json_from_s3(bucket_name, 'R_FoodInspections.json')


# Convert JSON to DataFrame
Restaurants = pd.DataFrame(restaurants_data)
Inspections = pd.DataFrame(inspections_data)


# Merge the dataframes on the 'HSISID' column
merged_df = pd.merge(Restaurants, Inspections, on='HSISID')

# Convert the date column to datetime format
merged_df['date'] = pd.to_datetime(merged_df['DATE_'])

# Sort by 'HSISID' and 'date' to prepare for filtering
merged_df.sort_values(['HSISID', 'date'], ascending=[True, False], inplace=True)

# Drop duplicates, keeping the first (latest) entry for each 'HSISID'
data = merged_df.drop_duplicates(subset='HSISID', keep='first')

# Create a safe_name column for URL usage
data.loc[:, 'safe_name'] = data['name'].str.lower().str.replace(' ', '-').str.replace('/', '-').str.replace('&', 'and')


# Extract all unique categories
all_categories = set()
for item in data['alias']:
    all_categories.update(item.split(', '))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Check if the username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.')
            return redirect(url_for('signup'))

        # Create a new user and set the password
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful. You can now log in.')
        return redirect(url_for('login'))
    
    return render_template('signup.html')



@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Query the database for the user
        user = User.query.filter_by(username=username).first()

        if user and user.verify_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Login failed. Check your username and password.')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    return f'Hello, {current_user.username}!'


@app.route('/')
def index():
    mapbox_access_token = os.getenv('MAPBOX_ACCESS_TOKEN')
    username = current_user.username if current_user.is_authenticated else None
    return render_template('index.html',
                           mapbox_access_token=mapbox_access_token,
                           username=username)

@app.route('/search', methods=['POST'])
def search():
    search_query = request.form['search_query']
    search_name = request.form.get('search_name', '')  # Add search_name input
    search_category = request.form.get('category', '')  # Add category input

    if not search_query and not search_name:
        return jsonify({
            'message': 'Please enter a city name or a restaurant name.'
        })

    page = int(request.form.get('page', 1))  # Default to page 1 if not provided
    results_per_page = 10

    # Filter data by city, name, and/or category
    filtered_data = data

    if search_query:
        filtered_data = filtered_data[filtered_data['city'].str.contains(search_query, na=False, case=False)]

    if search_name:
        filtered_data = filtered_data[filtered_data['name'].str.contains(search_name, na=False, case=False)]
    
    if search_category:
        filtered_data = filtered_data[filtered_data['alias'].str.contains(search_category, na=False, case=False)]

    # Replace NaN with empty strings for all columns
    filtered_data = filtered_data.fillna('')

    # Convert phone number to string, handle numeric values correctly
    filtered_data['phone'] = filtered_data['phone'].apply(
        lambda x: str(int(x)) if isinstance(x, (int, float)) and not pd.isna(x) else ''
    )

    # Handle any other non-string values if needed
    filtered_data['zip_code'] = filtered_data['zip_code'].astype(str)

    total_items = len(filtered_data)

    if total_items == 0:
        return jsonify({
            'message': f'No results for "{search_query}", "{search_name}", or "{search_category}"'
        })

    # Extract unique categories from the filtered data
    filtered_categories = set()
    for item in filtered_data['alias']:
        filtered_categories.update(item.split(', '))

    # Paginate results
    start = (page - 1) * results_per_page
    end = start + results_per_page
    paginated_data = filtered_data.iloc[start:end]

    # Prepare response
    results = {
        'data': paginated_data.to_dict(orient='records'),
        'total_pages': (len(filtered_data) // results_per_page) + (1 if len(filtered_data) % results_per_page > 0 else 0),
        'categories': sorted(filtered_categories)
    }

    return jsonify(results)

@app.route('/categories', methods=['GET'])
def get_categories():
    return jsonify(sorted(all_categories))

@app.route('/restaurant/<HSISID>', methods=['GET'])
def restaurant_detail(HSISID):
    restaurant = merged_df[merged_df['HSISID'] == int(HSISID)]
    if restaurant.empty:
        abort(404)

    # Extracting inspection details
    inspection_data = merged_df[merged_df['HSISID'] == int(HSISID)]
    # Format dates
    # Ensure the 'date' column is in datetime format
    inspection_data['date'] = pd.to_datetime(inspection_data['date'])

    # Format dates
    inspection_data['date'] = inspection_data['date'].dt.strftime('%Y-%m-%d')

    inspection_dates = inspection_data['date'].tolist()
    inspection_scores = inspection_data['SCORE'].tolist()
    inspection_details = inspection_data[['date', 'TYPE', 'SCORE']].to_dict(orient='records')

    return render_template('restaurant_detail.html',
                           restaurant=restaurant.iloc[0],
                           inspection_dates=inspection_dates,
                           inspection_scores=inspection_scores,
                           inspection_details=inspection_details)



@app.route('/get_inspection_details', methods=['POST'])
def get_inspection_details():
    V_HSISID = request.form.get('HSISID')
    inspect_date = request.form.get('inspect_date')

    # Initialize DynamoDB resource
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('FoodInspectionViolation')

    # Query the DynamoDB table using the GSI
    response = table.query(
        IndexName='HSISID-INSPECTDATE-index',  # Replace with your actual GSI name
        KeyConditionExpression=Key('HSISID').eq(int(V_HSISID)) & Key('INSPECTDATE').eq(inspect_date)
    )

    # Extract required fields
    items = response.get('Items', [])
    inspection_details = [{
        'CRITICAL': item['CRITICAL'],
        'CATEGORY': item['CATEGORY'],
        'COMMENTS': item['COMMENTS']
    } for item in items]

    return jsonify({
        'violation_count': len(inspection_details),
        'violation_details': inspection_details
    })

if __name__ == '__main__':
    app.run(debug=True)
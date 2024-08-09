from flask import Flask, render_template, request, jsonify, abort
import pandas as pd
import os
import boto3
from boto3.dynamodb.conditions import Key
import json
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)

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

@app.route('/')
def index():
    mapbox_access_token = os.getenv('MAPBOX_ACCESS_TOKEN')
    return render_template('index.html',mapbox_access_token=mapbox_access_token)

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
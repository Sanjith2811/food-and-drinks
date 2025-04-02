from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import boto3
import uuid
import os
import time
import zipfile
import requests
from botocore.exceptions import ClientError
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = "your_secret_key"

# AWS Configuration
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
lambda_client = boto3.client('lambda', region_name='us-east-1')
apigateway = boto3.client('apigateway', region_name='us-east-1')

# Tables
users_table = dynamodb.Table('loginuser')
inventory_table_name = "InventoryTable"
orders_table_name = "OrdersTable"
inventory_table = dynamodb.Table(inventory_table_name)
orders_table = dynamodb.Table(orders_table_name)

# IAM Role and Resource Names
ROLE_ARN = 'arn:aws:iam::924223248821:role/LabRole'
LAMBDA_FUNCTION_NAME = 'FoodAndDrinksApi'
DYNAMODB_TABLE_NAME = "NewFoodAndDrinksTable"  # Kept for backward compatibility
API_NAME = 'FoodAndDrinksAPI'

# Create loginuser table
def create_loginuser_table():
    try:
        dynamodb.meta.client.describe_table(TableName='loginuser')
        print("Table 'loginuser' already exists.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print("Creating table 'loginuser'...")
            dynamodb.create_table(
                TableName='loginuser',
                KeySchema=[{'AttributeName': 'username', 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': 'username', 'AttributeType': 'S'}],
                ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
            )
            time.sleep(10)
            print("Table 'loginuser' created successfully!")
        else:
            raise e

# Create InventoryTable
def create_inventory_table():
    existing_tables = [table.name for table in dynamodb.tables.all()]
    if inventory_table_name not in existing_tables:
        table = dynamodb.create_table(
            TableName=inventory_table_name,
            KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'id', 'AttributeType': 'S'}],
            ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
        )
        table.wait_until_exists()
        print(f"Table '{inventory_table_name}' created successfully.")
    else:
        print(f"Table '{inventory_table_name}' already exists.")

# Create OrdersTable
def create_orders_table():
    existing_tables = [table.name for table in dynamodb.tables.all()]
    if orders_table_name not in existing_tables:
        table = dynamodb.create_table(
            TableName=orders_table_name,
            KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'id', 'AttributeType': 'S'}],
            ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
        )
        table.wait_until_exists()
        print(f"Table '{orders_table_name}' created successfully.")
    else:
        print(f"Table '{orders_table_name}' already exists.")

# Initial food and drinks data
food_items = [
    {"id": "1", "name": "Pizza", "price": 10, "restaurant": "Soporonos", "quantity": 50},
    {"id": "2", "name": "Burger", "price": 5, "restaurant": "McDonald's", "quantity": 50},
    {"id": "3", "name": "Doner Kebab", "price": 8, "restaurant": "Soporonos", "quantity": 50},
    {"id": "4", "name": "Popcorn", "price": 3, "restaurant": "Burger King", "quantity": 50},
    {"id": "5", "name": "Cake", "price": 12, "restaurant": "Cake World", "quantity": 50}
]

drink_items = [
    {"id": "6", "name": "Coca Cola", "price": 2, "restaurant": "Mini Juice Shop", "quantity": 50},
    {"id": "7", "name": "Pepsi", "price": 2, "restaurant": "Fresh Juice", "quantity": 50},
    {"id": "8", "name": "Mirinda", "price": 2, "restaurant": "Asian Shop", "quantity": 50},
    {"id": "9", "name": "Fanta", "price": 2, "restaurant": "Quality Juice", "quantity": 50},
    {"id": "10", "name": "Orange Juice", "price": 4, "restaurant": "Juice Point", "quantity": 50}
]

def insert_initial_inventory():
    for item in food_items + drink_items:
        inventory_table.put_item(Item=item)

# Lambda and API Gateway setup (unchanged)
def create_dynamodb_table():
    try:
        dynamodb.meta.client.describe_table(TableName=DYNAMODB_TABLE_NAME)
        print(f"Table '{DYNAMODB_TABLE_NAME}' already exists.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"Creating table '{DYNAMODB_TABLE_NAME}'...")
            dynamodb.create_table(
                TableName=DYNAMODB_TABLE_NAME,
                KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': 'id', 'AttributeType': 'S'}],
                ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
            )
            time.sleep(10)
            print(f"Table '{DYNAMODB_TABLE_NAME}' created successfully!")
        else:
            raise e

def get_lambda_function():
    try:
        response = lambda_client.get_function(FunctionName=LAMBDA_FUNCTION_NAME)
        print(f"Lambda function '{LAMBDA_FUNCTION_NAME}' already exists.")
        return response['Configuration']['FunctionArn']
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return None
        raise

def create_lambda_function():
    lambda_arn = get_lambda_function()
    if lambda_arn:
        return lambda_arn
    lambda_code = """
import json
def lambda_handler(event, context):
    food_and_drinks = {
        "food": [
            {"name": "Pizza", "price": "$10"},
            {"name": "Burger", "price": "$5"},
            {"name": "Doner Kebab", "price": "$8"},
            {"name": "Popcorn", "price": "$3"},
            {"name": "Cake", "price": "$12"}
        ],
        "drinks": [
            {"name": "Coca Cola", "price": "$2"},
            {"name": "Pepsi", "price": "$2"},
            {"name": "Mirinda", "price": "$2"},
            {"name": "Fanta", "price": "$2"},
            {"name": "Orange Juice", "price": "$4"}
        ]
    }
    return {
        'statusCode': 200,
        'headers': {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        'body': json.dumps(food_and_drinks)
    }
"""
    zip_file_path = 'lambda_function.zip'
    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr('food_drinks_api.py', lambda_code)
    with open(zip_file_path, 'rb') as f:
        zip_file = f.read()
    lambda_response = lambda_client.create_function(
        FunctionName=LAMBDA_FUNCTION_NAME,
        Runtime='python3.8',
        Role=ROLE_ARN,
        Handler='food_drinks_api.lambda_handler',
        Code={'ZipFile': zip_file},
        Timeout=30,
        MemorySize=128
    )
    print(f"Lambda function '{LAMBDA_FUNCTION_NAME}' created!")
    return lambda_response['FunctionArn']

def get_api_gateway():
    response = apigateway.get_rest_apis()
    for api in response.get('items', []):
        if api['name'] == API_NAME:
            print(f"API Gateway '{API_NAME}' already exists.")
            return api['id']
    return None

def create_api_gateway(lambda_arn):
    api_id = get_api_gateway()
    if api_id:
        return f"https://do4ef5aifl.execute-api.us-east-1.amazonaws.com/Prod/food-drinks"
    api_response = apigateway.create_rest_api(
        name=API_NAME,
        description='API for Food and Drinks'
    )
    api_id = api_response['id']
    root_resource_id = apigateway.get_resources(restApiId=api_id)['items'][0]['id']
    resource_response = apigateway.create_resource(
        restApiId=api_id,
        parentId=root_resource_id,
        pathPart='food-drinks'
    )
    resource_id = resource_response['id']
    apigateway.put_method(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='GET',
        authorizationType='NONE'
    )
    region = "us-east-1"
    uri = f'arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations'
    apigateway.put_integration(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='GET',
        type='AWS_PROXY',
        integrationHttpMethod='POST',
        uri=uri
    )
    print(f"API Gateway '{API_NAME}' created with ID: {api_id}")
    return f"https://do4ef5aifl.execute-api.us-east-1.amazonaws.com/Prod/food-drinks"

# Routes
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        response = users_table.get_item(Key={'username': username})
        user = response.get('Item')
        if user and user['password'] == password:
            session['user'] = username
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users_table.put_item(Item={'username': username, 'password': password})
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    api_url = "https://do4ef5aifl.execute-api.us-east-1.amazonaws.com/Prod/food-drinks"
    response = requests.get(api_url)
    food_and_drinks_data = response.json() if response.status_code == 200 else {}
    return render_template('dashboard.html', food_and_drinks=food_and_drinks_data)

@app.route('/food-and-drinks', methods=['GET'])
def get_food_and_drinks():
    api_url = "https://do4ef5aifl.execute-api.us-east-1.amazonaws.com/Prod/food-drinks"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        return jsonify(data)
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to fetch data: {str(e)}"}), 500

@app.route('/movies', methods=['GET'])
def get_movie_list():
    MOVIE_API_URL = "https://jd8ojhgd63.execute-api.us-east-1.amazonaws.com/dv"
    try:
        response = requests.get(MOVIE_API_URL)
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify({"error": "Failed to fetch movie data"}), 500
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Error fetching movie data: {str(e)}"}), 500

@app.route('/api/data', methods=['GET'])
def get_data():
    my_data = [{"id": 1, "name": "Sample Item 1"}, {"id": 2, "name": "Sample Item 2"}]
    try:
        return jsonify({"status": "success", "data": my_data}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/add_item', methods=['POST'])
def add_item():
    data = request.json
    item_id = str(uuid.uuid4())
    data['id'] = item_id
    inventory_table.put_item(Item=data)
    return jsonify({"message": "Item added successfully!", "item": data}), 201

@app.route('/delete_item/<string:item_id>', methods=['DELETE'])
def delete_item(item_id):
    response = inventory_table.delete_item(Key={'id': item_id})
    return jsonify({"message": f"Item with ID {item_id} deleted!"}), 200

@app.route('/place_order', methods=['POST'])
def place_order():
    data = request.json
    username = data.get('username')
    items = data.get('items', {})  # Dictionary {item_id: quantity}

    if not username or not items:
        return jsonify({"error": "Username and items are required"}), 400

    order_id = str(uuid.uuid4())
    total_price = 0
    order_items = []

    for item_id, quantity in items.items():
        response = inventory_table.get_item(Key={'id': item_id})
        if 'Item' in response:
            item = response['Item']
            if item['quantity'] < quantity:
                return jsonify({"error": f"Not enough stock for {item['name']}"}), 400
            order_items.append({"id": item_id, "name": item['name'], "price": item['price'], "quantity": quantity})
            total_price += item['price'] * quantity
            inventory_table.update_item(
                Key={'id': item_id},
                UpdateExpression="SET quantity = quantity - :q",
                ExpressionAttributeValues={":q": quantity}
            )

    orders_table.put_item(
        Item={
            'id': order_id,
            'username': username,
            'items': order_items,
            'total_price': total_price,
            'status': 'pending'
        }
    )

    invoice = {
        "username": username,
        "order_id": order_id,
        "items": order_items,
        "total_price": total_price
    }
    return jsonify({"message": "Order placed successfully!", "invoice": invoice}), 201

@app.route('/get_inventory', methods=['GET'])
def get_inventory():
    try:
        response = inventory_table.scan()
        items = response.get('Items', [])
        return jsonify({"items": items}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/cancel_order/<string:order_id>', methods=['DELETE'])
def cancel_order(order_id):
    response = orders_table.get_item(Key={'id': order_id})
    if 'Item' not in response:
        return jsonify({"error": "Order not found"}), 404
    order = response['Item']
    for item in order['items']:
        inventory_table.update_item(
            Key={'id': item['id']},
            UpdateExpression="SET quantity = quantity + :q",
            ExpressionAttributeValues={":q": item['quantity']}
        )
    orders_table.delete_item(Key={'id': order_id})
    return jsonify({"message": f"Order {order_id} canceled, and stock restored!"}), 200

@app.route('/order')
def order():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('order.html')

if __name__ == "__main__":
    create_loginuser_table()
    create_inventory_table()
    create_orders_table()
    insert_initial_inventory()
    create_dynamodb_table()
    lambda_function_arn = create_lambda_function()
    api_url = create_api_gateway(lambda_function_arn)
    app.run(debug=True)
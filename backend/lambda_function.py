import json
import boto3

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('FoodDrinks')

def lambda_handler(event, context):
    action = event.get('action')

    if action == "get_food":
        response = table.scan()
        return {"statusCode": 200, "body": json.dumps(response['Items'])}

    elif action == "add_food":
        item = json.loads(event['body'])
        table.put_item(Item=item)
        return {"statusCode": 200, "body": "Food added successfully"}

    elif action == "delete_food":
        item_id = event['id']
        table.delete_item(Key={'id': item_id})
        return {"statusCode": 200, "body": "Food deleted successfully"}

    return {"statusCode": 400, "body": "Invalid request"}

"""Update bucket price history for test listings"""
from services.bucket_price_history_service import update_bucket_price

# Update price history for test buckets
silver_price = update_bucket_price(9)
gold_price = update_bucket_price(10)

print('Updated bucket prices:')
print(f'  Silver (Bucket 9): ${silver_price}')
print(f'  Gold (Bucket 10): ${gold_price}')

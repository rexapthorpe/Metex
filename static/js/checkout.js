function openSellerPopup(bucketId) {
    fetch(`/api/bucket/${bucketId}/cart_sellers`)
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('sellerDetails');
            container.innerHTML = '';

            data.forEach(seller => {
                const div = document.createElement('div');
                div.innerHTML = `
                    <p><strong>${seller.username}</strong></p>
                    <p>Price per coin: $${seller.price_per_coin}</p>
                    <p>Quantity: ${seller.quantity}</p>
                    <p>Rating: ${seller.rating.toFixed(2)} (${seller.num_reviews} reviews)</p>
                    <form method="POST" action="/cart/remove_seller/${bucketId}/${seller.seller_id}" onsubmit="return confirm('Remove this seller?');">
                        <button type="submit" class="btn btn-danger btn-sm">Remove Seller</button>
                    </form>
                    <hr>
                `;
                container.appendChild(div);
            });

            document.getElementById('sellerModal').style.display = 'block';
        });
}

function closeSellerPopup() {
    document.getElementById('sellerModal').style.display = 'none';
}

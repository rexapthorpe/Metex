# app.py
import config
from flask import Flask, redirect, url_for

# Route Blueprints
from routes.auth_routes import auth_bp
from routes.sell_routes import sell_bp
from routes.listings_routes import listings_bp
from routes.buy_routes import buy_bp
from routes.account_routes import account_bp
from routes.checkout_routes import checkout_bp
from routes.messages_routes import messages_bp
from routes.cart_routes import cart_bp
from routes.bid_routes import bid_bp
from routes.ratings_routes import ratings_bp
from routes.portfolio_routes import portfolio_bp



app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Configure OAuth (Google login)
# (Add your OAuth setup here, if needed)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(sell_bp)
app.register_blueprint(listings_bp, url_prefix='/listings')
app.register_blueprint(buy_bp)
app.register_blueprint(account_bp)
app.register_blueprint(checkout_bp)
app.register_blueprint(messages_bp)
app.register_blueprint(cart_bp)
app.register_blueprint(bid_bp)
app.register_blueprint(ratings_bp)
app.register_blueprint(portfolio_bp)


@app.route('/')
def index():
    return redirect(url_for('buy.buy'))

if __name__ == '__main__':
    app.run(debug=True)

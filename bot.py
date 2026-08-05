import os
from flask import Flask, redirect, request, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return "HMB BOT is running successfully!"

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if code:
        return f"Authorization code received successfully! Code: {code}"
    return "Authorization failed or cancelled.", 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
